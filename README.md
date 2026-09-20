# 琴葉姉妹とライサント島の伝説 —— 简体中文汉化（过程 / 技术 / 步骤 全记录）

> 本仓库记录这次汉化的**完整过程、用到的技术、操作步骤与产物**，并附上可直接复用的工具脚本与补丁文件。
> 游戏：琴葉姉妹とライサント島の伝説（DeskClub，v1.00.04，Steam AppID 1569180）
> 引擎：Unity 2019.1.13f1（**32 位播放器**，Mono，TextMeshPro 2.0.1，uGUI）

---

## 1. 项目概况

| 项 | 内容 |
|---|---|
| 起点 | 已有汉化补丁 alpha1.2（只替换了 Gyate 一个字体资产） |
| 目标 | 在补丁基础上：**消除口口口**、修正描边/行距/字体观感、尽量做成"纯资产、零依赖"的补丁 |
| 约束 | 最小修改；未改动的对象必须**字节级不变**；每一步都要**程序化验证**；随时可一键回滚 |

---

## 2. 问题诊断（全部基于实测，非推断）

| 结论 | 证据 |
|---|---|
| 口口口的根因 = 补丁**只替换了 Gyate 一个字体** | 原版 730,248 B / 6985 字形 → 补丁 **212,484 B / 2172 字形**；另外 3 个字体字节数完全未变 |
| 补丁文件膨胀 36,490,412 → 170,190,332 B 的原因 | 工具把 2 张 8192² 图集改为**内联**（图集对象 payload 67,108,988 B） |
| 补丁作者只改过 1 个材质数值 | 逐属性 diff：`Gyate-Luminescence SDF Material (0x1a)` 的 `_OutlineWidth` `0.0 → 0.3`（白色描边） |
| 游戏实际使用 5 个字体 | 运行时日志：Gyate / Makinas-4-Square / RiiPopkkR / Stick_Regular / GDhwGoJA-OTF112b2 |
| 行距过宽的原因 | 我们初版烘焙采信了源字体的 1.448 em 行高；补丁字体是 1.000 em |
| 字体观感差异的原因 | 补丁用**黑体 SimHei**；我们初版误用了圆体（ChillRoundGothic） |

---

## 3. 技术路线：**资产级拼接**（不依赖运行时注入也能修主字体）

```
自烤 TMP 字体资产 + 图集像素
        │  Unity 2019.1.13f1 批处理：FontBakerTwo.Bake → BundleBuilder.Build
        ▼
以原补丁的 sharedassets0.assets 为输入
        │  splice_fonts.py：字体 payload 追加到文件尾并改对象表；图集像素原地覆盖
        ▼
产出 .test 文件 → verify_splice.py 独立校验 → install_assetfix.ps1 安装（自动备份）
```

**核心设计原则**：只替换「字体 payload + 图集像素」两处，**材质的 PPtr 与材质↔图集配对一律不动** ——
这样描边、颜色、每场景样式全部沿用原补丁（这正是原补丁描边正确的原因）。
字体资产的名字、`m_Script`、`m_Enabled`、尾部权重表都照抄目标文件，避免任何悬空引用。

---

## 4. 关键技术真值（都从实证反推）

### 4.1 容器格式（SerializedFile v19 / UnityFS v6）
* 头部 4 个 u32 是**大端**；元数据段（类型表/对象表）是**小端**；对象条目 **20 字节**；`绝对偏移 = byteStart + dataOffset`
* UnityFS 头里是**两个** null 结尾字符串；`flags & 0x3F` 是目录信息(blocksInfo)的压缩方式，数据块各带自己的 flags
* **坑**：自家 bundle 内嵌 SerializedFile 的版本串可能不以 4 字节对齐结束（`2019.1.13f1\n2`，13 字节）→
  盲目 `align(4)` 会让元数据整体错位 2 字节、解析跑到文件尾。修法：候选起点两处都试，用"对象表全落在文件内"判定

### 4.2 Texture2D 像素锚点
payload 中值为 `8192×8192` 的 i32 **不止一个**（`m_CompleteImageSize` 也等于它）。
**真锚点判据**：取最后一个匹配，且其后恰好 12 字节全零（`m_StreamData` 为 0）、前 4 字节为零。
校验方式：与外部"黄金像素"（烘焙产出的 `twobake_atlas.bin`）逐字节一致才算对。

### 4.3 TMP_FontAsset 序列化布局（逐字段实测）
```
+0   m_GameObject PPtr(12)      +12  m_Enabled u8=1 + 3 填充
+16  m_Script PPtr(12)          +28  m_Name 字符串
     TMP_Asset: hashCode(i32) / material(PPtr12) / materialHashCode(i32)
     TMP_FontAsset: m_Version("1.1.0") / m_SourceFontFileGUID(32字符) / ...
尾部 [-272: i32 count=10][-268:-28: m_FontWeightTable 240B][-28:-16: null PPtr][-16: 样式4值]
```
* 原版 **Makinas / GDhwGoJA 的尾部比我们多 4 字节**（count 在 `-268`）→ 字段集相同但数据长度不同，
  替换时必须**按索引搜索**定位权重表，不能用固定偏移
* 我们的工程资产把 `m_FontWeightTable` 全填成"指向自己"→ 直接搬过去就是**悬空引用**，修法：固定字段一律照抄目标

### 4.4 TMP 材质口径公式（从原版 4 组数据反推并逐条验证）
* `_GradientScale = padding + 1`（padding 10 → 11；padding 5 → 6）
* `_ScaleRatioA = 1 − 1/_GradientScale`（10 → 0.909091；5 → 0.833333）
* `_ScaleRatioB = _ScaleRatioC = _ScaleRatioA × (0.8125 − _FaceDilate)`
  （验证：×0.8125=0.738636 ✓ ×0.6125=0.556818 ✓ ×0.5625=0.511364 ✓ ×0.6625=0.602273 ✓）
* 描边实际宽度 = `_OutlineWidth × _ScaleRatioA` → 这几个系数是**几何口径，不是风格值**

### 4.5 字体识别：用度量剖面，不靠肉眼
补丁字体 FaceInfo `ascent=146.0938/170=0.85938`、`descent=-23.9062/170=0.14063` = `220/256`、`36/256`
→ 源字体 `unitsPerEM=256, hhea=(220,-36)` → 本机唯一符合的是 **`C:\Windows\Fonts\simhei.ttf`（黑体）**（距离 0.0228，
其他候选 0.21~0.52）。

### 4.6 烘焙脚本的两个坑
1. **FaceInfo 取的是"最后加载的字面"**（= 补字字体）→ 烤完必须再跑 `patch_faceinfo.py` 把 FaceInfo 校正到补丁比例
2. **Unity 启动器会提前返回**（编辑器仍在跑）；工程若需全量重编译，第一次 `-batchmode -quit -executeMethod` 只编译不执行方法，**要跑第二遍**

---

## 5. 操作步骤

### 5.1 字体烘焙（Unity 批处理）
1. 配方：`fontsource.txt`（主字体，如 `Assets/Fonts/simhei.ttf`）、`fontsource_filler.txt`（补字，如 NotoSansCJKsc）、`charset.txt`
2. `Unity.exe -batchmode -quit -projectPath <工程> -executeMethod FontBakerTwo.Bake`
3. `... -executeMethod BundleBuilder.Build`（输出未压缩且无类型树的 bundle）
4. 产出：`Assets/BakedFonts/KotonohaCreator.asset`、`twobake_atlas.bin`（黄金像素）、`twobake_report.tsv`

### 5.2 拼接进游戏资产
1. `bundle_serialized.py` 从 bundle 提取 SerializedFile
2. `splice_fonts.py --target <游戏资产> --our <提取文件> --out <测试文件>` →
   替换字体 payload（指向目标图集/材质）+ 原地覆盖图集像素 + FaceInfo 校正 + 描边值调整
3. `verify_splice.py` 独立校验：对象数不变、未改动对象**逐字节一致**、图集像素 == 黄金、无悬空引用、`fileSize` 头一致
4. `install_assetfix.ps1 -TestFile <测试文件>` 安装（自动备份 + 哈希核对）

### 5.3 打包与交付
1. `build_dist.py` 生成"一键安装包"目录（`kotonoha_Data\` + `BepInEx\` + `install.bat/ps1` + `manifest.tsv` + 中文说明）
2. 交付前**干跑**：安装 → 逐文件哈希核对 → 回滚 → 原文件哈希还原 + 删除新增文件
3. 打包成 ZIP（Win10 自带 `tar -a -c -f x.zip`，比 Compress-Archive 快很多）

### 5.4 运行时辅助插件（BepInEx）
* 作用：给"非主字体"建运行时代理、短标签去折行/自动缩字、布局诊断（`[OVERFLOW]`/`[SHRINK]`/`[WRAPFIX]`/`[GAP]`）
* 编译：`build_plugin.ps1`（用 dnSpy 自带 Roslyn，无需 .NET SDK）

---

## 6. 产物清单

| 产物 | 说明 |
|---|---|
| `kotonoha_Data\sharedassets0.assets` | 5 个字体全部资产级（Gyate/Makinas/Rii/Stick + Gyate 图集） |
| `kotonoha_Data\resources.assets` | GDhwGoJA 字体 + **图集已内联**（不再需要 919 MB 的 `.resS`） |
| `kotonoha_Data\Managed\Assembly-CSharp.dll` | 文本层修正 |
| `kotonoha_Data\level0 / level4 / level121` | 文本层修正 |
| `BepInEx\plugins\KotonohaCNFont.dll` | 排版微调插件（可关，不影响中文字形） |
| `BepInEx\plugins\kotonoha_font.bundle` | SimHei 字体包（运行时字体源） |
| 安装包 | 完整版 zip（含 BepInEx）/ 纯静态版 zip（仅 `kotonoha_Data`，零依赖） |

---

## 7. 已解决问题 / 已知问题

**已解决** ✓ 口口口消失 · 描边正确 · 字体=黑体 SimHei · 行距 1.0 em · 5 字体资产级 · 24 条短标签单行化

**已知** ✗ 道具名「薄荷巧克力色的翅膀」显示两行 —— 经排查该名字**不在游戏可枚举的文本对象里**
（同界面其他文本都正常），属另一条文本/渲染路径，暂不修；不影响可读性。

---

## 8. 回滚

| 方式 | 命令 |
|---|---|
| 只停插件 | `powershell -File toggle_plugin.ps1 -Off` |
| 回滚资产 | `powershell -File install_assetfix.ps1 -Uninstall`（取最近备份） |
| 回到验收过的状态 | 用 `backup\snapshot_*` 覆盖游戏目录对应文件 |
| 交付包安装的 | 游戏目录 `_cn_backup_<时间戳>\rollback.ps1` |

---

## 9. 目录结构

```
docs/    汉化过程与技术的详细文档（01~14 号）
tools/   解析/拼接/校验/打包/编译 全套脚本（纯标准库 Python + PowerShell）
plugin/  BepInEx 插件源码（C#）
dist/    一键安装包（见 Releases）
```
