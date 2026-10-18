"""Export isolated MMD model copies, with portable FBX material connections."""
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import bpy

from .materials import create_material, describe_material, opaque_polygon_indices


def find_root(obj):
    while obj is not None:
        if getattr(obj, "mmd_type", None) == "ROOT":
            return obj
        obj = obj.parent
    return None


def model_objects(context):
    roots = {find_root(obj) for obj in context.selected_objects}
    roots.discard(None)
    if not roots and context.active_object:
        root = find_root(context.active_object)
        if root:
            roots.add(root)
    if len(roots) != 1:
        raise ValueError("Select one mmd_tools model (its root, armature, or mesh)")
    root = roots.pop()
    children = list(root.children_recursive)
    meshes = [o for o in children if o.type == "MESH" and getattr(o, "mmd_type", "NONE") == "NONE"]
    arms = [o for o in children if o.type == "ARMATURE"]
    if not meshes or len(arms) != 1:
        raise ValueError("The selected MMD model must contain meshes and exactly one armature")
    return meshes + arms


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._")[:60] or "model"


def reject_legacy_manifest(target):
    manifest = target.with_suffix(".materials.json")
    if not manifest.is_file():
        return
    try:
        report = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return
    if (isinstance(report, dict) and report.get("producer") == "mmd_unity_exporter"
            and report.get("schema_version") == 1 and report.get("file") == target.name):
        raise ValueError(
            f"发现同名旧版导出清单：{manifest}。请先备份并移出该清单及其 .meta，"
            "再重新导出，避免旧 Unity 接收脚本覆盖新材质；插件不会自动清理用户项目。"
        )


@contextmanager
def unity_alpha_channel():
    # Unity URP detects textured transparency through TransparentColor.
    # The stock Blender mapping is TransparencyFactor; restore it for all other exports.
    from io_scene_fbx import export_fbx_bin
    original = export_fbx_bin.PRINCIPLED_TEXTURE_SOCKETS_TO_FBX
    if ("alpha_texture", b"TransparencyFactor") not in original:
        raise RuntimeError("This Blender FBX exporter version has an unsupported alpha mapping")
    export_fbx_bin.PRINCIPLED_TEXTURE_SOCKETS_TO_FBX = tuple(
        (socket, b"TransparentColor" if socket == "alpha_texture" else target)
        for socket, target in original
    )
    try:
        yield
    finally:
        export_fbx_bin.PRINCIPLED_TEXTURE_SOCKETS_TO_FBX = original


def export_model(context, filepath, alpha_policy="ALL_OPAQUE", add_backfaces=True):
    if alpha_policy not in {"ALL_OPAQUE", "PRESERVE_BLEND", "ALL_BLEND"}:
        raise ValueError("Unknown export alpha policy: " + str(alpha_policy))
    if context.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before exporting")
    if not hasattr(bpy.types.Object, "mmd_type"):
        raise ValueError("Enable mmd_tools and select an imported MMD model")
    sources = model_objects(context)
    descriptions = {}
    for obj in sources:
        if obj.type == "MESH":
            for slot in obj.material_slots:
                if slot.material not in descriptions:
                    descriptions[slot.material] = describe_material(slot.material, alpha_policy)
    target = Path(filepath).expanduser().resolve()
    if target.suffix.lower() != ".fbx":
        raise ValueError("The output filename must end in .fbx")
    if not context.window:
        raise RuntimeError("A Blender window context is required")
    reject_legacy_manifest(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    original_scene = context.window.scene
    original_view_layer = context.window.view_layer
    matrices = {obj: obj.matrix_world.copy() for obj in sources}
    images, materials, objects, data = [], [], [], []
    temporary_scene = None
    report = {"file": target.name, "alpha_policy": alpha_policy, "add_backfaces": add_backfaces,
              "backface_faces": 0, "materials": [], "meshes": sum(o.type == "MESH" for o in sources)}
    # Stage the entire bundle first so missing-image/export failures don't damage an existing export.
    with tempfile.TemporaryDirectory(prefix=".mmd_unity_", dir=target.parent) as staging:
        staging = Path(staging)
        texture_id = _safe_name(target.stem) + "_" + hashlib.sha256(target.stem.encode("utf-8")).hexdigest()[:12]
        texture_dir = Path("Textures") / texture_id
        (staging / texture_dir).mkdir(parents=True)
        try:
            converted, material_infos, baked_images, opaque_variants = {}, {}, {}, {}
            for index, (source, description) in enumerate(descriptions.items()):
                relative = texture_dir / f"{index:03d}_{_safe_name(source.name)}.png"
                material, info = create_material(description, staging / relative, images, materials, alpha_policy)
                converted[source] = material
                info["texture"] = relative.as_posix()
                report["materials"].append(info)
                material_infos[source] = info
                baked_images[source] = images[-1]
            temporary_scene = bpy.data.scenes.new("MMD Unity Export Temporary")
            temporary_scene.unit_settings.scale_length = original_scene.unit_settings.scale_length
            mapping = {}
            for source in sources:
                clone = source.copy()
                objects.append(clone)
                clone.name = source.name + "_Unity"
                clone.data = source.data.copy()
                data.append(clone.data)
                clone.animation_data_clear()
                temporary_scene.collection.objects.link(clone)
                clone.hide_viewport = False
                clone.hide_render = False
                clone.hide_select = False
                clone.constraints.clear()
                mapping[source] = clone
            for source, clone in mapping.items():
                clone.parent = mapping.get(source.parent)
                clone.matrix_world = matrices[source]
                if clone.type == "MESH":
                    for slot in clone.material_slots:
                        slot.material = converted[slot.material]
                    # One atlas can mix solid clothing with soft hair/lace. Solid
                    # faces need their own depth-writing material in Unity.
                    for index, slot in enumerate(source.material_slots):
                        original = slot.material
                        info = material_infos[original]
                        if (alpha_policy != "PRESERVE_BLEND"
                                or not descriptions[original]["image_alpha"] or info["alpha_mode"] != "BLEND"):
                            continue
                        solid = opaque_polygon_indices(clone.data, index, baked_images[original])
                        if not solid:
                            continue
                        if original not in opaque_variants:
                            variant = converted[original].copy()
                            materials.append(variant)
                            variant.name = converted[original].name + "_Opaque"
                            shader = variant.node_tree.nodes.get("Principled BSDF")
                            for link in list(shader.inputs["Alpha"].links):
                                variant.node_tree.links.remove(link)
                            shader.inputs["Alpha"].default_value = 1
                            opaque_variants[original] = variant
                            report["materials"].append({**info, "material": variant.name,
                                "alpha_mode": "OPAQUE", "transparent": False, "has_alpha_pixels": False})
                        variant = opaque_variants[original]
                        target_slot = clone.data.materials.find(variant.name)
                        if target_slot < 0:
                            target_slot = len(clone.data.materials)
                            clone.data.materials.append(variant)
                        for face in solid:
                            clone.data.polygons[face].material_index = target_slot
                    for modifier in list(clone.modifiers):
                        if modifier.type == "ARMATURE":
                            modifier.object = mapping.get(modifier.object)
                        else:
                            clone.modifiers.remove(modifier)
                    if clone.data.shape_keys:
                        clone.data.shape_keys.animation_data_clear()
                        for key in clone.data.shape_keys.key_blocks:
                            key.value = 0
                else:
                    clone.data.pose_position = "REST"
                    for bone in clone.pose.bones:
                        for constraint in list(bone.constraints):
                            bone.constraints.remove(constraint)
            if add_backfaces:
                # Keep independent vertices so opposite faces do not cancel smooth normals.
                # Copy the converted mesh after material splitting and armature remapping.
                for front in tuple(objects):
                    if front.type != "MESH" or not front.data.polygons:
                        continue
                    backside = front.copy()
                    objects.append(backside)
                    backside.data = front.data.copy()
                    data.append(backside.data)
                    backside.name = front.name + "_Backfaces"
                    mesh = backside.data
                    normals = {}
                    if mesh.has_custom_normals:
                        normals = {
                            (face.index, mesh.loops[index].vertex_index):
                                tuple(-value for value in mesh.corner_normals[index].vector)
                            for face in mesh.polygons for index in face.loop_indices
                        }
                    mesh.flip_normals()
                    # flip_normals changes winding and corner data, but not custom normals.
                    if normals:
                        mesh.normals_split_custom_set([
                            normals[(face.index, mesh.loops[index].vertex_index)]
                            for face in mesh.polygons for index in face.loop_indices
                        ])
                    mesh.update()
                    temporary_scene.collection.objects.link(backside)
                    report["meshes"] += 1
                    report["backface_faces"] += len(mesh.polygons)
            context.window.scene = temporary_scene
            for clone in objects:
                clone.select_set(True)
            context.view_layer.objects.active = objects[0]
            context.view_layer.update()
            with (unity_alpha_channel() if any(m["alpha_mode"] == "BLEND" for m in report["materials"]) else nullcontext()):
                result = bpy.ops.export_scene.fbx(
                    filepath=str(staging / target.name),
                    use_selection=True, object_types={"MESH", "ARMATURE"},
                    use_mesh_modifiers=False, add_leaf_bones=False,
                    use_armature_deform_only=False, bake_anim=False,
                    apply_unit_scale=True, axis_forward="-Z", axis_up="Y",
                    path_mode="RELATIVE", embed_textures=False,
                )
            if "FINISHED" not in result:
                raise RuntimeError("Blender FBX export was cancelled")
            # Publish only files created by this export. The FBX is published last.
            for texture in dict.fromkeys(info["texture"] for info in report["materials"]):
                destination = target.parent / texture
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / texture, destination)
            os.replace(staging / target.name, target)
        finally:
            context.window.scene = original_scene
            context.window.view_layer = original_view_layer
            for obj in objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            for block in data:
                if isinstance(block, bpy.types.Mesh):
                    bpy.data.meshes.remove(block)
                else:
                    bpy.data.armatures.remove(block)
            if temporary_scene:
                bpy.data.scenes.remove(temporary_scene)
            for material in materials:
                bpy.data.materials.remove(material)
            for image in images:
                bpy.data.images.remove(image)
    return report
