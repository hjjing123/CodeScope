# Java SAST 工具开发蓝图 (基于逆向工程分析)

本文档整合了对 `ChanziSAST` 的框架分析与数据流分析结果。旨在为您从零开发一款类似的、基于图数据库的静态代码审计工具提供完整的技术参考。

---

## 1. 系统架构概览 (System Architecture)

该工具是一个 **本地优先 (Local-First)** 的桌面端应用，采用 **"三级存储架构"** 来平衡性能与分析深度。

### 1.1 核心技术栈 (Tech Stack)
| 组件 | 选型建议 | 理由 |
| :--- | :--- | :--- |
| **开发语言** | **Java 21+** | 利用新版 JDK 的性能优势（如虚拟线程）处理大量文件 IO。 |
| **GUI 框架** | **JavaFX** | 配合 `AtlantaFX` (主题) 和 `RichTextFX` (代码高亮) 构建现代化界面。 |
| **代码解析** | **Eclipse JDT** (或 JavaParser) | 需要强大的符号解析能力（解决"变量在哪里定义"的问题）。 |
| **图数据库** | **Neo4j Embedded** | 嵌入式部署，无需用户安装数据库服务；利用 Cypher 进行路径查询。 |
| **全文检索** | **Apache Lucene** | 用于快速根据文件名、内容定位代码行，弥补图数据库处理大文本的短板。 |

---

## 2. 数据存储设计 (Data Storage Design)

工具运行时会生成三个关键的数据目录，分别承担不同职责。在开发时应模仿此设计：

### Tier 1: 语义索引 (Semantic Workspace)
*   **目录**: `..._lspdata`
*   **技术**: Eclipse JDT Language Server (Workspace)
*   **作用**: 作为一个临时的 IDE 工作区。编译器在此处分析类路径（Classpath），构建类型层级（Type Hierarchy）。
*   **开发启示**: 不要试图自己写正则匹配代码。必须启动一个编译器环境（如 JDT 或 JavaParser 的 `JavaSymbolSolver`），才能准确识别 `userDao.find()` 到底调用了哪个类的方法。

### Tier 2: 文本索引 (Text Index)
*   **目录**: `..._lucene`
*   **技术**: Apache Lucene
*   **作用**: 存储文件路径、代码原始内容、行号索引。
*   **开发启示**: **不要把源代码存入 Neo4j！** 图数据库擅长处理关系，不擅长存储大文本。当用户点击漏洞报告时，通过 Lucene 毫秒级定位到 `UserMapper.xml:15`。

### Tier 3: 污点图谱 (Taint Graph)
*   **目录**: `..._neo4j`
*   **技术**: Neo4j Embedded (PageCache / Record Store)
*   **作用**: 存储代码属性图 (CPG - Code Property Graph)。
*   **开发启示**: 使用嵌入式模式 (`GraphDatabaseService`)，直接在进程内读写文件，避免网络开销。

---

## 3. 图模型设计 (Graph Schema)

这是核心商业机密部分。通过逆向 Cypher 规则，我们推导出其 Schema 设计采用了 **"标签预计算" (Pre-computed Labels)** 策略。

### 3.1 节点 (Nodes)
*   **`Class`**: 类定义。
*   **`Method`**: 方法定义。
*   **`Arg`**: 方法参数或变量。

### 3.2 关系 (Relationships)
*   `(:Method)-[:CALLS]->(:Method)`: 核心调用链。
*   `(:Class)-[:HAS_METHOD]->(:Method)`: 从属关系。
*   `(:Method)-[:HAS_ARG]->(:Arg)`: 参数关系。
*   `(:Arg)-[:DATA_FLOW]->(:Arg)`: (高级) 变量间的数据流向。

### 3.3 关键标签策略 (Labeling Strategy)
工具在 **入库阶段** 就通过 AST 分析打好了语义标签，而不是在查询阶段动态判断。

| 标签名 | 含义 | 触发条件 (ETL 逻辑) |
| :--- | :--- | :--- |
| **`SpringControllerArg`** | 污点源 (Source) | 方法有 `@RequestMapping` 且参数无 `@Ignore`。 |
| **`DubboServiceArg`** | 污点源 (Source) | 类有 `@DubboService` 或实现 Dubbo 接口。 |
| **`Exec` / `ProcessBuilder`** | 危险汇点 (Sink) | 方法调用名为 `Runtime.exec` 或 `ProcessBuilder.start`。 |

---

## 4. 核心流水线 (Processing Pipeline)

如果您要复刻该工具，请遵循以下处理流程：

### 阶段一：预处理 (Preprocessing)
1.  **环境检查**: 检查 JDK 版本，配置内存 (Heap/PageCache)。
2.  **LSP 初始化**: 启动 JDT/JavaParser，扫描项目依赖 (`lib/*.jar`)，确保所有类都能被解析。

### 阶段二：ETL (Extract, Transform, Load)
这是最耗时的步骤。
1.  **遍历 AST**: 访问每一个 Java 文件。
2.  **语义增强**:
    *   *伪代码*:
        ```java
        if (method.hasAnnotation("RequestMapping")) {
            Node argNode = graph.createNode("Arg");
            argNode.addLabel("SpringControllerArg"); // 关键！预打标
        }
        ```
3.  **图写入**: 使用 Neo4j 的 Java API 将节点和关系写入磁盘。
4.  **文本索引**: 同时将文件信息写入 Lucene。

### 阶段三：检测 (Detection)

1.  **加载规则**: 读取 `.cypher` 文件。
2.  **执行算法**:
    *   查询: `MATCH p = shortestPath((src:SpringControllerArg)-[:CALLS*..10]->(sink:Exec)) RETURN p`
    *   由于 `src` 和 `sink` 的标签已经预先打好，Neo4j 只需要做路径搜索，速度极快。

---

## 5. 开发起步建议 (Getting Started)

1.  **第一步**: 熟悉 **JavaParser**。写一个小程序，能够解析 Java 文件并识别出所有带有 `@Controller` 注解的方法参数。
2.  **第二步**: 引入 **Neo4j Embedded**。将第一步识别出的参数作为节点存入数据库。
3.  **第三步**: 实现 **调用图构建**。解析方法体内的函数调用，在 Neo4j 中建立 `CALLS` 关系。
4.  **第四步**: 编写 **Cypher 查询**。验证是否能通过图查询找到从 Controller 到 Runtime.exec 的路径。
