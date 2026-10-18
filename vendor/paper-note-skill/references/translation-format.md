# 双语逐句翻译格式

## 总原则

所有翻译都直接写进同一个阅读入口里，顺序固定为：

1. 英文原句
2. 紧接中文译句
3. 下一句

不要把中文放进脚注。
默认保持原段落结构，不要把中文译句改成单独起段的块。

## 写法

英文原句继续使用原有句子功能宏，例如：

```latex
\bgsent{Large language models have changed the writing workflow.}
```

下一行紧接对应中文句子：

```latex
\zhbgsent{大语言模型已经改变了写作工作流。}
```

这里的关键要求不是“有中文就行”，而是中英文对应句子要保持同色，而且中文应直接接在英文后面，不要打断原段落流。

如果英文句子本身不需要功能色，也可以写成：

```latex
Original sentence here.
\zhtrans{这里写对应的中文句子。}
```

## 宏对应关系

优先使用成对宏，保持中英两句功能一致：

- `\bgsent` -> `\zhbgsent`
- `\gapsent` -> `\zhgapsent`
- `\questionsent` -> `\zhquestionsent`
- `\methodsent` -> `\zhmethodsent`
- `\resultsent` -> `\zhresultsent`
- `\claimsent` -> `\zhclaimsent`
- `\structsent` -> `\zhstructsent`
- `\relatedsent` -> `\zhrelatedsent`
- `\keysent` -> `\zhkeysent`

如果没有对应功能色，就用：

- `\zhtrans{...}`

但 `\zhtrans{...}` 只应用在无句子功能色的翻译文本，例如普通标题补译、说明性短句、非句级补充。只要英文原句已经用了句子功能宏，中文就应跟着用对应的 `\zh*sent`。

## `\pnote` 粒度

- 句子功能色仍然逐句标。
- `\pnote` 默认不再一句一个。
- 如果相邻几句承担同一种功能，并且仍在同一个局部推进块里，就把它们合并成一个 `\pnote`。
- 合并后的 `\pnote` 放在这组中英句对里最后一句中文后面。

## 翻译边界

- 标题、正文、附录文字、方法说明、实验叙述默认都翻。
- caption 默认不翻译，图注和表注保持原英文。
- references、参考文献条目、BibTeX 数据、纯引用 key、`thebibliography` 环境、`\bibliography{...}` / `\printbibliography` 驱动出来的部分默认不翻。
- 纯宏定义、纯路径性或工具性内容可以不翻。
- 数学公式、符号、引用键、交叉引用标签保持原样。
- 图表内 axis label、图中文字或复杂 caption 结构默认不碰，除非用户单独要求处理图表文字。
- 不要为了“像中文论文”而重写论证结构；中文版仍应一一对应英文原文的推进顺序。

## `\pnote` 的位置

如果当前入口启用了 `\pnote`，它默认跟在对应功能块最后一句中文后面。

推荐结构：

```latex
\resultsent{Our method improves F1 by 3.2 points.}
\zhresultsent{我们的方法把 F1 提高了 3.2 个点。}
\pnote{结果|保留}{数字和比较对象都齐了。}
```

## 标题

如需在同一份 PDF 中给标题补中文，可优先使用：

- `\bititle{English Title}{中文标题}`

caption 默认保持原英文，不再引入单独的 caption 翻译宏。
