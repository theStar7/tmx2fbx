# MMD Unity FBX Exporter

针对**[mmd tools](https://github.com/MMD-Blender/blender_mmd_tools)插件**开发，为 **mmd_tools 已导入的 MMD 模型**制作的 Blender 导出插件，将受支持的基础材质转换为 FBX 可识别的直接贴图连接。输出 **一个 FBX 和 Textures 文件夹**

[下载 1.0.0 安装包](https://github.com/theStar7/tmx2fbx/releases/tag/v1.0.0) · [更新记录](CHANGELOG.md) · [MIT 许可证](LICENSE)

## 功能

- 在 Blender 中选择 MMD 模型后导出 FBX，随包输出可移植 PNG 贴图。
- 提供全部不透明、全部半透明、手动选择材质分类三种整体模式。
- 可选增加反向面，默认开启；转换只作用于临时导出副本。
- 面向 Unity URP 原生材质导入，保留受支持的基础色、UV、骨架蒙皮和顶点形态键。

## 安装


1. 安装 [mmd tools](https://github.com/MMD-Blender/blender_mmd_tools) 插件用于导入pmx模型
2. 与 Release 界面下载并选择 `mmd_unity_exporter-1.0.0.zip`，压缩包无需解压。在 Blender 的扩展安装界面选择 **Install from Disk**。
2. 启用插件及 mmd tools插件，使用 MMD Tools 插件导入 PMX。
最低声明版本为 Blender 4.2；本版目标环境为 Blender 4.5、MMD Tools 4.5.1、Unity 2022.3、URP 14。

## 导出

在 **3D 视图按 N → MMD → Unity FBX 导出** 打开下面的面板。按照需求更改设置，最后点击 **MMD → Unity FBX**。导出fbx模型

![插件默认导出面板：全部不透明、增加反向面与导出按钮](https://raw.githubusercontent.com/theStar7/tmx2fbx/24ea3a0da150d6b4a83b1831651cff3a6d8f5274/docs/images/panel-default.png)

*图 1：默认面板。下方逐材质分类置灰是正常现象，只有切换到手动模式才可编辑。配图为 Blender 4.5.14 的实际界面，仅展示操作位置。*

1. 选 MMD 模型的根对象、骨架或网格。
2. 打开 **N → MMD → Unity FBX 导出**，在导出按钮上方的 **整体导出模式**下拉框中选择 **全部不透明 / 全部半透明 / 手动选择材质分类**。选中根对象、骨架或网格均可选择；默认全部不透明。
3. 在同一侧栏选择是否 **增加反向面**；默认勾选；不需要时可取消勾选，保持原几何。已有场景明确保存的关闭选择不会被强行覆盖。此选项与三种透明模式独立。
4. 点击 **MMD → Unity FBX**，选择任意输出目录并导出。
5. 将 FBX 与整个 Textures 文件夹一起放入 Unity 的 Assets，保持相对位置不变。

```text
YourModel.fbx
Textures/
  YourModel_<stable-id>/
    000_material.png
    ...
```

贴图目录及文件名保持稳定；重新导出会覆盖同名 FBX 及其对应的派生贴图。请为不同模型使用不同文件名。源图不会被覆盖。

## 三种材质导出模式

点击 **整体导出模式** 下拉框，可在以下三种模式间切换；这是整个模型的导出策略。

![整体导出模式下拉框：全部不透明、全部半透明、手动选择材质分类](https://raw.githubusercontent.com/theStar7/tmx2fbx/24ea3a0da150d6b4a83b1831651cff3a6d8f5274/docs/images/export-modes.png)

*图 2：整体模式入口位于导出按钮上方，不需要去文件保存窗口寻找。*

| 模式 | 行为 |
| --- | --- |
| **全部不透明（默认）** | 忽略所有透明度，包括镂空和半透明；派生 PNG 的 Alpha 设为 1，材质不连接透明通道。 |
| **全部半透明** | 所有材质都输出透明连接，包括 Alpha 全为 1 的贴图和无贴图纯色材质；保留原有效 Alpha。 |
| **手动选择材质分类** | 使用各材质的自动、不透明或半透明分类；自动分类仍可推断透明度。AlphaClip材质输出为不透明材质。 |

**全部不透明**与**全部半透明**覆盖逐材质分类。全部半透明模式中，Alpha=1 的部分仍呈实心外观，但也进入透明队列、关闭深度写入。

不透明材质通过正常深度测试和深度写入处理遮挡。手动选择材质分类及全部半透明仍有 Unity 原生透明排序限制，不能保证任意视角、骨骼动作或相交透明面都正确。全部半透明也不承诺实心外观部分的遮挡稳定性。

## 背面处理选项

在侧栏导出按钮上方设置 **增加反向面**，选中根对象、骨架或网格均可设置；侧栏按钮与 File → Export 读取同一场景选择。

- **关闭**：保持原几何，Unity 使用默认背面剔除，薄片背面可能不可见。
- **开启（默认）**：为每个非空导出网格额外生成一个 `_Backfaces` 网格，复制其顶点、UV、材质分配、蒙皮权重及形态键，并反转面朝向；存在自定义法线时按对应面角反转法线。反向网格沿用同一骨架及转换后的材质，不新增材质或贴图。

新增几何仅作用于临时导出副本，不修改或保存源模型。该选项与三种透明模式独立，不依赖 Unity 脚本或关闭背面剔除。它没有厚度，不做挤出或边缘封口。

开启后通常使网格对象、顶点和三角形数量约翻倍，增加文件体积、蒙皮与绘制开销；已含双层几何的模型也会复制。透明背面可能加重重叠及排序问题，不保证任意视角或动作下排序正确。

本版在反转面朝向时单独处理自定义面角法线，尚未进行实际运行验证。

## Blender 中的材质分类

先将侧栏的 **整体导出模式**设为 **手动选择材质分类**，再选中网格，在 **N → MMD → Unity FBX 导出 → 当前材质 → 材质分类**设置。其他整体模式会将此分类控件置灰；根对象没有当前材质时不显示逐材质分类，但仍显示整体模式。

![手动模式下的材质分类下拉框：自动、不透明、半透明](https://raw.githubusercontent.com/theStar7/tmx2fbx/24ea3a0da150d6b4a83b1831651cff3a6d8f5274/docs/images/material-classification.png)

*图 3：先选“手动选择材质分类”，再选中模型网格及其目标材质，在“当前材质”下方选择分类。截图中的“面”是当前选中材质的名称，不是固定选项。*

逐材质分类仅影响**手动选择材质分类**模式：

- **自动**：计算当前受支持节点链的有效 Alpha；完全实心为不透明，透明贴图的可见像素中至少 90% 接近实心时推断为镂空，其余保留混合。
- **不透明**：忽略 Alpha，原镂空孔洞也会填满；合并原“不透明”和“镂空”选项。
- **半透明**：保留有效 Alpha。

旧版已保存的镂空分类按不透明读取，旧版半透明分类保留原含义；不会仅因升级而重写源材质分类数据。

自动分类是贴图统计推断，不能完全识别美术意图；误判时可手动纠正。

在手动选择材质分类模式中，同一材质混用实心衣物和柔软透明部分时，会检查逐面 UV 覆盖。仅在明确使用贴图 Alpha、单 UV 层、派生 PNG 对应矩形及 2 像素边界全部实心的情况下，追加共用原 PNG 的不透明材质槽，并断开该槽的透明连接。自动和显式半透明分类均允许此拆分；其余面保留混合。多 UV 或不能安全证明的面不作拆分。此检查基于基础 mip，不是任意距离或滤波条件下的完整透明证明。

全部不透明模式无需拆分；全部半透明模式禁止拆出不透明槽。

## Unity 原生接收

项目针对 URP 开发。由 Unity 自带导入器生成 Lit 材质。FBX 中的不透明材质不携带透明连接；半透明材质通过 `TransparentColor` 贴图连接声明。Lit 的 Blending Mode 沿用原生 Alpha 默认值。

不同 Unity 版本、项目导入偏好和已有材质映射可能影响结果。本版没有实际验证零操作导入或最终渲染行为。


## 转换范围与源保护

只在临时副本中转换，不保存原 blend，不修改源节点、贴图路径、UV、源材质槽或原面索引。保留基础色贴图、PMX 漫反射颜色、UV、材质对应关系、骨架、有效蒙皮权重及顶点形态键；输出静止骨架，形态键当前值归零但保留形态键，排除刚体、关节等辅助网格。

支持活动 Material Output 直连 MMDShaderDev 或 Principled BSDF。基础图支持直接 Image Texture 和标准 MMD Base UV；基础颜色处理不混入 Ambient、Toon 或 Sphere。全部不透明模式跳过不使用的 Alpha 链路，其他模式支持 Alpha 常量或同一基础图的 Alpha 输出，并计算受支持的基础 Alpha 乘积。

自定义基础色 Mapping、其他投影或贴图边界模式、基础色自定义节点等维持现有拒绝规则；需要 Alpha 的模式不支持任意自定义 Alpha 网络。基础贴图缺失会报错。无基础贴图的纯色材质生成 1×1 PNG。

不支持 MMD Toon、Sphere、高光语义、描边、材质 Morph、动画、IK 或物理求解；Unity 光照与 Blender/MMD 显示可能不同。

## 开发与打包

插件运行文件为 `blender_manifest.toml`、`__init__.py`、`materials.py`、`exporter.py`。发行 ZIP 另外包含 LICENSE 和本 README，共六项。

仓库仅收录当前插件与发布所需文件；

```text
mmd_unity_exporter/
  __init__.py
  blender_manifest.toml
  exporter.py
  materials.py
tools/
  package.py
docs/
  images/                  # README 实际界面截图
CHANGELOG.md
LICENSE
README.md
```

打包需要 Python 3.11 或更新版本（使用标准库 `tomllib`），无需安装第三方 Python 依赖。在仓库根目录执行：

```powershell
python tools/package.py
```

输出为 `dist/mmd_unity_exporter-1.0.0.zip`。`dist/` 不纳入源码仓库，安装包通过 GitHub Release 提供。插件运行于 Blender 自带 Python，不能直接用系统 Python 执行。

打包脚本只写入上述六项白名单文件，不运行测试、扩展校验或安装验证。修改发布版本时，应同步更新 `blender_manifest.toml` 中的 `version`、`__init__.py` 中的 `bl_info["version"]` 及使用说明。

## 许可证

插件源码使用 [MIT License](LICENSE)。MMD Tools、Blender、Unity 及用户模型、贴图各自遵循其原有许可；本仓库不分发模型素材。
