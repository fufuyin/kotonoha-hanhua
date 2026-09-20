# 12 UABEA 操作手册（把我们的字体写进原补丁的 sharedassets0.assets）

> 目标：**保持原补丁的全部对象/材质/图集↔材质配对不变**，只把「Gyate 的 TMP 字体资产」与「它的 8192² 图集像素」
> 换成我们的（7898 字符、寒蝉圆黑体 + 补字、padding 10 / `_GradientScale` 11）。
> 这样描边、颜色、每语言材质天然正确，且不再需要 BepInEx。

## 0. 我已准备好的东西（你不用动）

| 用途 | 路径 |
|---|---|
| **要打开的源 bundle**（含我们的字体资产，**有类型树**，UABEA 能 dump） | `F:\Steam\...\kotonoha\BepInEx\plugins\kotonoha_font.bundle` |
| 我们的图集（PNG，8bit 灰度 8192×8192） | `F:\Application\Unity\twobake_atlas.png` |
| 我们的图集（RAW Alpha8，备用） | `F:\Application\Unity\twobake_atlas.bin` |
| 要改的目标（原补丁） | `D:\桌面\补丁alpha1.2-放在kotonoha_Data下\sharedassets0.assets` |
| 工具（已在本机） | `D:\桌面\光阳岛\新建文件夹 (4)\UABEAvalonia.exe` |

> ⚠️ **不要直接改原补丁文件夹里的文件**。先把它拷一份到
> `F:\Steam\...\kotonoha\_hanhua\work\sharedassets0.assets`，我们只改副本。

## 1. 导出我们的字体资产 JSON

1. 双击 `UABEAvalonia.exe`
2. `File → Open` → 选 `BepInEx\plugins\kotonoha_font.bundle`（较大，读入要十几秒）
3. 左侧资产列表里找 **MonoBehaviour**，名字应是 **`KotonohaCreator`**（可用列表上方的过滤框输入名字）
4. 选中它 → **Export Dump** → 存成 `our_font.json`（放桌面即可）

## 2. 打开目标文件并导出「游戏自己那份」字体资产 JSON

5. `File → Open` → 选副本 `_hanhua\work\sharedassets0.assets`
6. 找 **MonoBehaviour** 里那个 **TMP 字体资产**：列表里它的大小约 **212 KB**，名字含
   `Gyate-Luminescence`（若没有名字列，就按大小找、或搜 `Gyate`）
7. 选中 → **Export Dump** → 存成 `game_font.json`

## 3. 改引用（关键一步，只有两个数字）

在 `game_font.json` 里找到这两处，记下它们的 `m_PathID`（一长串数字）：

- `"m_AtlasTextures"` 数组的第 1 个元素的 `"m_PathID"`（指向游戏自己的 Gyate 图集）
- `"m_Material"` 的 `"m_PathID"`（指向游戏自己的 Gyate 材质）

然后在 `our_font.json` 里，把**同样这两处**的 `m_PathID` 替换成上面记下的值（用文本编辑器的替换功能，注意只改这两个位置）。

> 这一步的作用：让我们的字体资产「指向游戏自己的图集与材质」，从而保持 **材质↔图集配对不变** —— 这正是原补丁描边/颜色正确的机制。
> 如果你愿意，把 `game_font.json` 和 `our_font.json` 给我，我直接改好还给你，省掉手工替换的风险。

## 4. 导入字体资产

8. 回到已打开的 `sharedassets0.assets`，仍选中那个 TMP 字体资产
9. **Import Dump** → 选改好的 `our_font.json`（会弹窗让你确认，若有 "SerializedReference 不支持" 之类提示先截图告我）

## 5. 导入图集像素

10. 在同一文件里找 **Texture2D `Gyate-Luminescence SDF Atlas`**（8192×8192）
11. **先用 `Plugins → Texture` 里的 `Save .png` 导出一张**（确认导出尺寸/通道），再 **`Load .png`** → 选
    `F:\Application\Unity\twobake_atlas.png`
12. 若报格式/通道不匹配：把第 11 步导出的那张 PNG 发我，我按它的实际格式（单通道/Alpha8 等）重新生成一张；必要时改走 RAW 方案

## 6. 保存并回填

13. `File → Save`（写回 `_hanhua\work\sharedassets0.assets`）
14. 保存后**先别启动游戏**，把这个文件的**大小**告诉我（原补丁是 170,190,332 字节）——我会做程序化校验：
    对象数仍为 **193**、大小变化符合预期、字体资产回读字符数 **7898 / 7897**、`padding=10`、`_GradientScale=11`
15. 校验通过后再把它复制到 `kotonoha_Data\sharedassets0.assets`（原文件已有备份），启动游戏验收：
    - 口口口是否消失
    - 开始页/金币等描边是否与「很完善那版」一致
    - 菜单角色语言是否不再乱码

## 备注

* 这份 UABEA 的 CLI 子命令只有 `batchexportbundle` / `batchimportbundle` / `applyemip`，**MonoBehaviour 的 dump/import 只能走界面**，所以这一步必须你点。
* 任何一步弹窗报错，**先截图/抄文字给我**再继续，不要自行重试覆盖（这一步是唯一会写 170MB 资产文件的操作）。
* 原补丁文件保持不动（我们不覆盖它），所以任何时候都能回退。
