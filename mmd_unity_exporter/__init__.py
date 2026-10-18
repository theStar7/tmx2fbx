"""MMD Tools companion exporter for Unity URP."""
import traceback

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .exporter import export_model, find_root

bl_info = {
    "name": "MMD Unity FBX Exporter",
    "author": "MMD Unity Exporter Contributors",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > MMD; File > Export",
    "description": "Export MMD base textures and transparency for Unity URP",
    "category": "Import-Export",
}


# Keep saved enum values stable when changing display order.
_ALPHA_POLICY_ITEMS = [("ALL_OPAQUE", "全部不透明", "忽略全部透明度，包括镂空和半透明", 0),
               ("ALL_BLEND", "全部半透明", "全部使用透明渲染模式，保留有效 Alpha，不统一降低透明度", 2),
               ("PRESERVE_BLEND", "手动选择材质分类", "使用各材质的自动、不透明或半透明分类", 1)]


def _get_material_alpha_mode(material):
    value = material.get("mmd_unity_alpha_mode", 0)
    # Old cutout (2) has the same output as opaque (1); do not rewrite source data.
    return 1 if value == 2 else value


def _set_material_alpha_mode(material, value):
    material["mmd_unity_alpha_mode"] = value


class MMDUNITY_OT_export(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mmd_unity_fbx"
    bl_label = "MMD → Unity FBX"
    bl_description = "导出当前 MMD 模型及基础材质贴图，保留原始场景"
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})
    alpha_policy: EnumProperty(
        name="材质导出模式",
        description="选择本次 FBX 导出的透明策略，不修改源材质",
        items=_ALPHA_POLICY_ITEMS,
        default="ALL_OPAQUE",
        options={"SKIP_SAVE"},
    )

    add_backfaces: BoolProperty(
        name="增加反向面",
        description="为导出副本增加反向网格，使薄片背面可见；增加模型开销且不解决透明排序",
        default=True,
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, event):
        if not self.properties.is_property_set("alpha_policy"):
            self.alpha_policy = context.scene.mmd_unity_export_alpha_policy
        if not self.properties.is_property_set("add_backfaces"):
            self.add_backfaces = context.scene.mmd_unity_export_add_backfaces
        root = find_root(context.active_object)
        if root and not self.filepath:
            self.filepath = bpy.path.clean_name(root.name) + ".fbx"
        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Unity URP / Lit · 基础材质", icon="MATERIAL")
        layout.prop(self, "alpha_policy")
        if self.alpha_policy != "ALL_OPAQUE":
            layout.label(text="半透明仍有排序限制", icon="INFO")
        if self.alpha_policy == "PRESERVE_BLEND":
            layout.label(text="使用 Blender 中的逐材质分类")
        layout.label(text="仅输出 FBX 和 Textures，无需 Unity 接收脚本")
        layout.prop(self, "add_backfaces")
        layout.label(text="原始 MMD 材质和场景保持不变")

    def execute(self, context):
        context.scene.mmd_unity_export_alpha_policy = self.alpha_policy
        context.scene.mmd_unity_export_add_backfaces = self.add_backfaces
        try:
            result = export_model(context, self.filepath, self.alpha_policy, self.add_backfaces)
        except Exception as error:
            traceback.print_exc()
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        blended = sum(m["alpha_mode"] == "BLEND" for m in result["materials"])
        opaque = len(result["materials"]) - blended
        backfaces = f"，新增 {result['backface_faces']} 个反向面" if self.add_backfaces else "，保持原几何"
        self.report({"INFO"}, f"已导出 {result['meshes']} 个网格、{opaque} 个不透明材质、{blended} 个透明渲染材质{backfaces}。请将 FBX 和 Textures 一起导入 Unity。")
        return {"FINISHED"}


class MMDUNITY_PT_export(bpy.types.Panel):
    bl_label = "Unity FBX 导出"
    bl_idname = "MMDUNITY_PT_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD"

    def draw(self, context):
        layout = self.layout
        if not hasattr(bpy.types.Object, "mmd_type"):
            layout.label(text="请先启用 MMD Tools", icon="ERROR")
        layout.label(text="选中 MMD 模型的根对象、骨架或网格")
        layout.label(text="整体导出模式")
        layout.prop(context.scene, "mmd_unity_export_alpha_policy", text="")
        if context.scene.mmd_unity_export_alpha_policy != "ALL_OPAQUE":
            layout.label(text="半透明仍有排序限制", icon="INFO")
        layout.prop(context.scene, "mmd_unity_export_add_backfaces", text="增加反向面")
        row = layout.row()
        row.operator_context = "INVOKE_DEFAULT"
        row.enabled = context.mode == "OBJECT" and find_root(context.active_object) is not None
        operator = row.operator(MMDUNITY_OT_export.bl_idname, icon="EXPORT")
        operator.alpha_policy = context.scene.mmd_unity_export_alpha_policy
        operator.add_backfaces = context.scene.mmd_unity_export_add_backfaces
        layout.label(text="按上方整体模式导出，默认全部不透明")
        layout.label(text="只需将 FBX 和 Textures 一起导入 Unity")
        material = getattr(context.active_object, "active_material", None)
        if material:
            layout.label(text="当前材质：" + material.name)
            row = layout.row()
            row.enabled = context.scene.mmd_unity_export_alpha_policy == "PRESERVE_BLEND"
            row.prop(material, "mmd_unity_alpha_mode", text="材质分类")
        layout.label(text="材质分类仅用于“手动选择材质分类”模式")


def _menu(self, context):
    operator = self.layout.operator(MMDUNITY_OT_export.bl_idname, text="MMD → Unity FBX (.fbx)")
    operator.alpha_policy = context.scene.mmd_unity_export_alpha_policy
    operator.add_backfaces = context.scene.mmd_unity_export_add_backfaces


_CLASSES = (MMDUNITY_OT_export, MMDUNITY_PT_export)


def register():
    bpy.types.Scene.mmd_unity_export_alpha_policy = EnumProperty(
        name="整体导出模式",
        description="用于本场景的 MMD Unity FBX 导出，覆盖或启用逐材质分类",
        items=_ALPHA_POLICY_ITEMS,
        default="ALL_OPAQUE",
    )
    bpy.types.Scene.mmd_unity_export_add_backfaces = BoolProperty(
        name="增加反向面",
        description="为导出副本增加反向网格，使薄片背面可见；增加模型开销且不解决透明排序",
        default=True,
    )
    bpy.types.Material.mmd_unity_alpha_mode = EnumProperty(
        name="材质分类",
        description="仅用于手动选择材质分类模式；自动推断或手动指定不透明、半透明",
        items=[("AUTO", "自动", "根据有效 Alpha 推断；镂空输出为不透明，渐变与固定透明保留混合", 0),
               ("OPAQUE", "不透明", "忽略 Alpha，正常深度遮挡，镂空孔洞填满", 1),
               ("BLEND", "半透明", "保留有效 Alpha；已证实实心的面可拆出不透明槽，仍有透明排序限制", 3)],
        default="AUTO",
        get=_get_material_alpha_mode,
        set=_set_material_alpha_mode,
    )
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(_menu)


def unregister():
    del bpy.types.Scene.mmd_unity_export_add_backfaces
    del bpy.types.Scene.mmd_unity_export_alpha_policy
    del bpy.types.Material.mmd_unity_alpha_mode
    bpy.types.TOPBAR_MT_file_export.remove(_menu)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
