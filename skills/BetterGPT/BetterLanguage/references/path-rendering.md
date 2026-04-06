# Path Rendering

## Goal

让文件、命令、生成产物的展示更短、更自然、更适合对话阅读。

## Default Rule

默认按这个优先级展示路径：

1. 文件名
2. 项目相对路径
3. 绝对路径

普通汇报里，优先使用前两种。

## Override Rule

如果当前平台或上层规则明确要求：

- 必须输出绝对路径
- 必须给出精确文件证据
- 当前界面会把相对路径变成不可点击或不可定位信息

则以上默认优先级可以被覆盖，直接使用绝对路径。

## When To Use File Name Only

以下场景优先只显示文件名：

- 已生成哪些文件
- 已修改哪些文件
- 已发现哪些产物
- 同一目录下文件名不会歧义

例如：

```text
已生成：
- index.md
- journal-1.md
```

## When To Use Relative Path

以下场景优先显示项目相对路径：

- 需要让用户知道文件位于哪个模块或目录
- 只写文件名可能歧义
- 当前任务和目录结构强相关

例如：

```text
已生成：
- .trellis/workspace/Administrator/index.md
- .trellis/workspace/Administrator/journal-1.md
```

## When Absolute Path Is Allowed

只有以下情况，才显示绝对路径：

- 用户明确要求完整路径
- 正在排查路径冲突
- 需要做精确证据引用
- 多个工作区或多个同名文件会导致歧义
- 当前任务本身就是定位磁盘真实位置

## Command Rendering

命令优先原样保留，但不要为了配合命令，额外重复输出一整段绝对路径。

例如：

```text
`python .trellis/scripts/task.py list` 可正常执行，返回 0 task(s)。
```

## Reporting Style

推荐写法：

```text
已生成：
- index.md
- journal-1.md

`python .trellis/scripts/task.py list` 可正常执行，返回 0 task(s)。
```

不要写成：

```text
已生成
C:\Users\Administrator\Desktop\Make-GPT-Great-Again\.trellis\workspace\Administrator\index.md
C:\Users\Administrator\Desktop\Make-GPT-Great-Again\.trellis\workspace\Administrator\journal-1.md
```
