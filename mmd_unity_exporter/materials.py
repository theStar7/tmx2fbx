"""Convert the supported MMD base-color subset into directly exportable materials."""
from pathlib import Path

import bpy
import numpy as np


def _value(shader, name, fallback):
    socket = shader.inputs.get(name)
    if socket is None:
        return fallback
    if socket.is_linked:
        raise ValueError(f"{shader.id_data.name}: {name} has custom/morph links; apply the desired base value before export")
    value = socket.default_value
    return tuple(value) if hasattr(value, "__len__") else float(value)


def describe_material(material, alpha_policy="ALL_OPAQUE"):
    if material is None or not material.use_nodes:
        raise ValueError("A material slot has no node material")
    target = {"BLENDER_EEVEE_NEXT": "EEVEE", "CYCLES": "CYCLES"}.get(bpy.context.engine, "ALL")
    output = material.node_tree.get_output_node(target) or material.node_tree.get_output_node("ALL")
    surface = output.inputs.get("Surface") if output else None
    shader = surface.links[0].from_node if surface and surface.is_linked else None
    principled = shader is not None and shader.type == "BSDF_PRINCIPLED"
    mmd = (shader is not None and shader.type == "GROUP"
        and shader.node_tree and (shader.name == "mmd_shader" or shader.node_tree.name.startswith("MMDShaderDev"))
        and "Diffuse Color" in shader.inputs)
    if not principled and not mmd:
        raise ValueError(f"{material.name}: Material Output Surface must connect directly to MMDShaderDev or Principled BSDF")
    base_name = "Base Color" if principled else "Base Tex"
    alpha_name = "Alpha" if principled else "Base Alpha"
    image = None
    base = shader.inputs.get(base_name)
    if base and base.is_linked:
        node = base.links[0].from_node
        if node.type != "TEX_IMAGE" or base.links[0].from_socket.name != "Color":
            raise ValueError(f"{material.name}: {base_name} must be connected directly to an Image Texture Color output")
        if node.projection != "FLAT" or node.extension != "REPEAT":
            raise ValueError(f"{material.name}: Only FLAT projection and REPEAT texture mapping are supported")
        vector = node.inputs["Vector"]
        if vector.is_linked:
            uv_link = vector.links[0]
            uv_node = uv_link.from_node
            standard_uv = (
                uv_node.type == "GROUP" and uv_node.name == "mmd_tex_uv"
                and uv_node.node_tree and uv_node.node_tree.name.startswith("MMDTexUV")
                and uv_link.from_socket.name == "Base UV"
            )
            if standard_uv:
                output = next((n for n in uv_node.node_tree.nodes if n.type == "GROUP_OUTPUT" and n.is_active_output), None)
                base_uv = output.inputs.get("Base UV") if output else None
                standard_uv = bool(base_uv and base_uv.is_linked
                    and base_uv.links[0].from_node.type == "TEX_COORD"
                    and base_uv.links[0].from_socket.name == "UV")
            if not standard_uv:
                raise ValueError(f"{material.name}: Custom UV mapping is unsupported; use the standard MMD Base UV")
        image = node.image
        if image is None:
            raise ValueError(f"{material.name}: Missing base texture image")
        if image.source not in {"FILE", "GENERATED"}:
            raise ValueError(f"{material.name}: Only static FILE or GENERATED textures are supported")
        if image.source == "FILE" and not image.packed_file:
            path = Path(bpy.path.abspath(image.filepath, library=image.library))
            if not path.is_file():
                raise ValueError(f"{material.name}: Missing texture: {path}")
        if not image.size[0] or not image.size[1]:
            raise ValueError(f"{material.name}: Missing or unreadable image: {image.name}")
    ignore_alpha = alpha_policy == "ALL_OPAQUE"
    alpha_socket = None if ignore_alpha else shader.inputs.get(alpha_name)
    image_alpha = False
    if alpha_socket and alpha_socket.is_linked:
        link = alpha_socket.links[0]
        if link.from_node.type != "TEX_IMAGE" or link.from_node != (base.links[0].from_node if base and base.is_linked else None) or link.from_socket.name != "Alpha":
            raise ValueError(f"{material.name}: {alpha_name} must come from the same base texture Alpha output")
        image_alpha = True
    return {
        "source": material,
        "alpha_mode": getattr(material, "mmd_unity_alpha_mode", "AUTO"),
        "image": image,
        "diffuse": (1, 1, 1) if principled else _value(shader, "Diffuse Color", (1, 1, 1, 1))[:3],
        "alpha": 1 if ignore_alpha or principled else _value(shader, "Alpha", 1),
        "base": _value(shader, base_name, (1, 1, 1, 1)) if image is None else (1, 1, 1, 1),
        "base_alpha": 1 if ignore_alpha or image_alpha else _value(shader, alpha_name, 1),
        "image_alpha": image_alpha,
        "factor": 1 if principled else _value(shader, "Base Tex Fac", 1),
    }


def create_material(description, filepath, images, materials, alpha_policy="ALL_OPAQUE"):
    source = description["source"]
    source_image = description["image"]
    width, height = tuple(source_image.size) if source_image else (1, 1)
    pixels = np.ones((width * height, 4), dtype=np.float32)
    if source_image:
        source_image.pixels.foreach_get(pixels.ravel())
    else:
        pixels[:, :3] = description["base"][:3]
    if source_image:
        color_space = source_image.colorspace_settings.name
        if not source_image.is_float and color_space == "sRGB":
            rgb = pixels[:, :3]
            pixels[:, :3] = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        elif not source_image.is_float and color_space not in {"Non-Color", "Linear", "Linear Rec.709"}:
            raise ValueError(f"{source.name}: Unsupported base texture color space: {color_space}")
        # Loaded float buffers store associated scene-linear RGB. Generated float
        # buffers are read as authored; byte buffers contain encoded straight RGB.
        if source_image.is_float and source_image.source == "FILE" and source_image.alpha_mode in {"STRAIGHT", "PREMUL"}:
            np.divide(pixels[:, :3], pixels[:, 3:4], out=pixels[:, :3], where=pixels[:, 3:4] > 0)
    pixels[:, :3] = (pixels[:, :3] * description["factor"] + 1 - description["factor"]) * description["diffuse"]
    if not description["image_alpha"]:
        pixels[:, 3] = description["base_alpha"]
    pixels[:, 3] *= description["alpha"]
    np.clip(pixels, 0, 1, out=pixels)
    has_alpha_pixels = bool(np.any(pixels[:, 3] < 1 - 1e-6))
    alpha_mode = description["alpha_mode"]
    if alpha_policy == "ALL_OPAQUE":
        alpha_mode = "OPAQUE"
    elif alpha_policy == "ALL_BLEND":
        alpha_mode = "BLEND"
    elif alpha_mode == "AUTO":
        # Cutout textures have mostly solid visible pixels and narrow soft edges.
        # Broad gradients (e.g. facial blush) must retain actual alpha blending.
        alpha = pixels[:, 3]
        visible = np.count_nonzero(alpha > 1 / 255)
        solid = np.count_nonzero(alpha >= 1 - 1 / 255)
        cutout = description["image_alpha"] and visible > 0 and solid >= 0.9 * visible
        alpha_mode = "OPAQUE" if not has_alpha_pixels else "CLIP" if cutout else "BLEND"
    if alpha_mode == "CLIP":
        alpha_mode = "OPAQUE"
    if alpha_mode == "OPAQUE":
        pixels[:, 3] = 1
    image = bpy.data.images.new(source.name + "_Unity_BaseMap", width=width, height=height, alpha=True, float_buffer=False)
    images.append(image)
    image.colorspace_settings.name = "sRGB"
    image.alpha_mode = "STRAIGHT"
    # Byte image buffers expect sRGB encoded, unassociated RGB. Using a float
    # image here makes Blender save a premultiplied 16-bit buffer and alters colors.
    rgb = pixels[:, :3]
    pixels[:, :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    image.pixels.foreach_set(pixels.ravel())
    image.file_format = "PNG"
    image.filepath_raw = str(filepath)
    image.save()

    material = bpy.data.materials.new(source.name + "_Unity")
    materials.append(material)
    material.use_nodes = True
    material.use_backface_culling = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (1, 1, 1, 1)
    shader.inputs["Alpha"].default_value = 1
    shader.inputs["Metallic"].default_value = 0
    shader.inputs["Roughness"].default_value = 0.7
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    # FBX only recognizes direct Image Texture -> Principled links.
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    if alpha_mode == "BLEND":
        material.node_tree.links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
        material.surface_render_method = "DITHERED"
    return material, {
        "source": source.name,
        "material": material.name,
        "transparent": alpha_mode == "BLEND",
        "has_alpha_pixels": alpha_mode == "BLEND" and has_alpha_pixels,
        "alpha_mode": alpha_mode,
    }


def opaque_polygon_indices(mesh, material_index, image):
    """Certify solid faces from the baked alpha, conservatively at base mip level."""
    # FBX/Unity uses UV0. Leave multi-UV meshes unchanged rather than guessing.
    if len(mesh.uv_layers) != 1:
        return []
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    alpha = pixels.reshape(height, width, 4)[:, :, 3]
    uv = mesh.uv_layers[0].data
    result = []
    for polygon in mesh.polygons:
        if polygon.material_index != material_index:
            continue
        points = np.array([uv[i].uv[:] for i in polygon.loop_indices]) * (width, height)
        # Inspect every texel in the unwrapped UV rectangle, including the filter
        # border. Wrap indices afterwards so crossing a repeat never hides holes.
        lower = np.floor(points.min(axis=0)).astype(np.int64) - 2
        upper = np.ceil(points.max(axis=0)).astype(np.int64) + 2
        x = (lower[0] + np.arange(min(width, upper[0] - lower[0] + 1))) % width
        y = (lower[1] + np.arange(min(height, upper[1] - lower[1] + 1))) % height
        if np.all(alpha[np.ix_(y, x)] >= 1 - 1e-6):
            result.append(polygon.index)
    return result
