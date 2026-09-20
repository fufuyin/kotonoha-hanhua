<div align="center">

# 琴葉姉妹とライサント島の伝説 · 简体中文汉化

**在既有汉化补丁 alpha1.2 的基础上重做字库：修掉口口口、修正描边与行距、字体统一为黑体**

[![Unity](https://img.shields.io/badge/Unity-2019.1.13f1-000000?logo=unity&logoColor=white)](https://unity.com)
[![Platform](https://img.shields.io/badge/Platform-Windows%2032--bit-0078D6?logo=windows&logoColor=white)]()
[![Engine](https://img.shields.io/badge/Engine-Mono%20%2B%20TextMeshPro%202.0.1-2C2C32?logo=unity&logoColor=white)]()
[![Font](https://img.shields.io/badge/Font-SimHei%20%2B%20Noto%20Sans%20CJK%20SC-E4572E)]()
[![Base](https://img.shields.io/badge/Base%20patch-alpha1.2-4C6EF5)]()
[![Status](https://img.shields.io/badge/Status-可玩%20%2F%20持续微调-2F9E44)]()

[**⬇️ 下载补丁**](https://github.com/fufuyin/kotonoha-hanhua/releases) ·
[技术文档](docs/) ·
[工具脚本](tools/) ·
[免责与署名](NOTICE.md)

</div>

---

## 📖 一句话说清

游戏原版的 TextMeshPro 字库**只有日文字形**，中文一显示就是 **口口口**。这个项目把游戏里
**5 个 TMP 字体全部换成中文可用字库**，并且**最小化改动**——只替换「字体数据 + 图集像素」两处，
材质、颜色、描边、图集配对全部沿用原补丁，因此不会破坏原有观感。

> 适用版本：v1.00.04（Steam AppID 1569180） · 32 位播放器 · Mono

---

## ✨ 这一版做了什么

| 问题 | 现象 | 处理 | 结果 |
|---|---|---|---|
| **口口口** | 中文全部显示为方框 | 更换 5 个 TMP 字体资产 | ✅ 消失 |
| **字库不全** | 缺字回退成方块 | 主字体 SimHei + Noto Sans CJK SC 补字 | ✅ 缺字 847 → **85** 个码位 |
| **描边过重** | 金币/按钮白边发糊 | 沿用原补丁的材质与描边值，只换字库 | ✅ 正常 |
| **行距过宽** | 文字行间空旷 | FaceInfo 校正到 **1.000 em** | ✅ 与原补丁一致 |
| **字体观感不对** | 与补丁风格不一致 | 用度量剖面反查出原字体是 **SimHei 黑体** | ✅ 风格统一 |
| **短标签折行** | 「敌人」等被拆两行 | BepInEx 插件做单行化 + 自动缩字 | ✅ 24 条已修 |

---

## 🚀 安装

<table>
<tr><th>版本</th><th>适合</th><th>包含</th></tr>
<tr><td><b>完整版（推荐）</b></td><td>绝大多数玩家</td><td>补丁资产 + BepInEx 运行库 + 排版微调插件</td></tr>
<tr><td><b>纯静态版</b></td><td>想零依赖 / 与别的插件共存</td><td>只有 <code>kotonoha_Data</code> 资产，中文照常显示</td></tr>
</table>

1. **关闭游戏**，先自行备份 `kotonoha_Data` 目录（安装脚本也会自动再备份一份）
2. 解压到游戏根目录（`kotonoha.exe` 所在目录），覆盖同名文件
3. 启动游戏

**回滚随时可做**：`toggle_plugin.ps1 -Off`（只停插件） / `install_assetfix.ps1 -Uninstall`（回滚资产） /
安装包内 `_cn_backup_<时间戳>\rollback.ps1`（一键还原）。

---

## 🔧 技术实现

### 流程

```text
① 烘焙：Unity 2019.1.13f1 批处理
   simhei.ttf（主）+ NotoSansCJKsc（补字）+ charset.txt
        └─► TMP_FontAsset + 8192² 图集像素 + 黄金像素校验文件

② 拼接：把字体写回游戏资产（只动两处）
   原补丁 sharedassets0.assets
        ├─ 字体 payload 追加到文件尾 + 改写对象表
        └─ 图集像素原地覆盖
        └─► .test 文件 ──► 独立校验 ──► 安装（自动备份）

③ 运行时（可选）：BepInEx 插件 KotonohaCNFont
   非主字体的运行时代理 + 短标签单行化 + 自动缩字 + 布局诊断
```

### 关键技术真值（全部实测反推，详见 [docs/](docs/)）

| 主题 | 结论 |
|---|---|
| **SerializedFile v19** | 头 4 个 u32 是**大端**；类型/对象表是**小端**；对象条目 20 字节；`绝对偏移 = byteStart + dataOffset` |
| **图集像素锚点** | 值为 8192² 的 i32 不止一个（`m_CompleteImageSize` 也是），真锚点 = **最后一个** 且后 12 字节全零 |
| **TMP 材质口径** | `_GradientScale = padding + 1`、`_ScaleRatioA = 1 − 1/_GradientScale`、`_ScaleRatioB/C = A × (0.8125 − _FaceDilate)` |
| **字体识别** | 用度量剖面反查：`ascent/descent = 220/256, 36/256` → `unitsPerEM=256` → 本机唯一符合的是 **SimHei** |
| **烘焙两个坑** | ① FaceInfo 会取到「补字字体」的值，需事后校正；② Unity 启动器提前返回，首次批处理只编译，要跑第二遍 |

> 所有写入操作都遵循：**先备份 → 程序化校验目标位置 → 写入 → 用独立脚本复验**。
> 过程中曾因手算十六进制偏移写错 67 MB，被硬断言拦下并完整还原，之后改为图集内联。

---

## 📂 仓库结构

```text
.
├── README.md            ← 你在这里（过程 / 技术 / 步骤 总览）
├── NOTICE.md            ← 免责声明、版权归属、署名
├── RELEASE_NOTES.md     ← Release 正文（发布脚本会自动读取）
├── docs/                ← 14 篇详细文档（诊断 → 方案 → 实施 → 总结）
│   └── README.md        ← 文档索引
├── tools/               ← 87 个脚本：解析 / 拼接 / 校验 / 打包 / 编译
├── plugin/              ← BepInEx 插件源码（C#）
├── unity/               ← 烘焙侧配方：字体源、charset、FontBakerTwo、BundleBuilder
└── dist/                ← 补丁压缩包（已被 .gitignore 排除，不进仓库）
```

**本仓库不含任何游戏原始资源或修改后的资产文件**（见 `.gitignore`：`*.assets / *.resS / *.bundle / *.ttf / *.zip` 等一律排除）。

---

## ❓ 常见问题

<details>
<summary><b>装完还是口口口？</b></summary>

先确认覆盖路径正确（必须盖到 `kotonoha_Data`，不是盖在游戏外层目录），再确认游戏版本是 v1.00.04。
若仍异常，用安装包里的 `rollback.ps1` 还原后重装。
</details>

<details>
<summary><b>能和其他 BepInEx 插件一起用吗？</b></summary>

可以。排版微调插件可通过 `toggle_plugin.ps1 -Off` 单独关掉，**关掉后中文字形不受影响**（字形是资产级的）。
或者直接用「纯静态版」，不含任何运行库。
</details>

<details>
<summary><b>会破坏原版存档吗？</b></summary>

不会。补丁只替换字体与图集，不触碰存档、脚本逻辑与游戏配置。
</details>

<details>
<summary><b>为什么补丁包有 100 MB 左右？</b></summary>

中文字库的 8192×8192 图集本身就有 64 MB（为覆盖全部汉字），加上内联后不再需要游戏原本 900 MB 的 `.resS`，总体仍是净收益。
</details>

---

## ⚠️ 已知问题

- 道具名「薄荷巧克力色的翅膀」显示为两行。该文本**不在游戏可枚举的文本对象范围内**（同界面其他文本都正常），
  已用白名单强制单行，其余同类文本待补。

---

## 🙏 致谢与声明

- **非官方汉化，仅供学习交流**。游戏版权归 **DeskClub / 原作者**所有，请通过 Steam 购买正版。
- **基础补丁 alpha1.2 由原补丁作者制作** —— 本项目在其成果之上仅替换字库，特此致谢。
  ⚠ 公开发布前请在此补上具体署名与出处（详见 [NOTICE.md](NOTICE.md)）。
- 字体：SimHei（Windows 自带）、Noto Sans CJK SC（SIL OFL 1.1） · 运行库：BepInEx 5（LGPL-2.1）

<div align="center">

**如果这个项目帮到你，给个 ⭐ 就是最大的支持**

</div>
