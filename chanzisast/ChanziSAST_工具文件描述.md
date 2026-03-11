# ChanziSAST 工具文件夹遍历与文件内容描述（尽量详尽、仅描述）

本文件用于“遍历并描述”`e:\chanzisast` 目录下的内容，目标是把该工具的目录结构、关键文件内容、以及运行/审计产物描述清楚，便于后续把本 MD 交给更高级的 AI 继续处理。

说明：
- 本文只做“文件/内容描述”，不做原理推导与优劣分析。
- 该目录以“已打包的桌面程序 + 大量依赖 JAR + 内置 Java Runtime + 内置 LSP(JDTLS) + 运行生成的数据目录/日志”为主。

---

## 1. 顶层目录总览（`e:\chanzisast\`）

顶层可见条目（排除大型子目录的展开）：
- 可执行文件：`ChanziSAST.exe`
- 文档（MD）：`SAST_Tool_Development_Blueprint.md`、`工具框架分析推导.md`、`日志目录分析报告.md`
- 小型二进制/密文类文件：`_e`、`_t`
- 数据库跟踪文件：`taskInfo.trace.db`
- 目录：`app\`、`lsp\`、`runtime\`、`logs\`、`Hello-Java-Sec_lspdata_20251211090724\`、`Hello-Java-Sec_lucene_20251211090724\`、`Hello-Java-Sec_neo4j_20251211090724\`

---

## 2. 根目录文件逐一描述

### 2.1 `ChanziSAST.exe`

- 路径：[ChanziSAST.exe](file:///e:/chanzisast/ChanziSAST.exe)
- 类型：Windows 可执行文件（桌面端启动入口）
- 文件大小：917,504 bytes
- 修改时间：2025/11/2 17:07:54
- 相关联配置：
  - 程序读取 `app/ChanziSAST.cfg` 获取主类与 classpath（见下文）。
  - 程序使用 `runtime/` 作为内置 Java Runtime（见下文）。

### 2.2 `_t`

- 路径：[_t](file:///e:/chanzisast/_t)
- 文件大小：472 bytes
- 修改时间：2025/12/11 9:21:04
- 内容形态：单行、base64/密文风格的字符串（示例为整行内容，无换行）。

### 2.3 `_e`

- 路径：[_e](file:///e:/chanzisast/_e)
- 文件大小：832 bytes
- 修改时间：2025/12/11 9:21:04
- 内容形态：单行、base64/密文风格的字符串（示例为整行内容，无换行）。

### 2.4 `taskInfo.trace.db`

- 路径：[taskInfo.trace.db](file:///e:/chanzisast/taskInfo.trace.db)
- 文件大小：213 bytes
- 修改时间：2025/12/11 8:56:52
- 内容：H2 数据库 JDBC 的 trace/异常记录，当前仅包含一次 “表不存在” 的 SQL 异常（完整内容如下）：

```text
2025-12-11 08:56:52.131379+08:00 jdbc[3]: exception
org.h2.jdbc.JdbcSQLSyntaxErrorException: Table "TASKS" not found (this database is empty); SQL statement:
SELECT 1 FROM TASKS FETCH FIRST ROW ONLY [42104-232]
```

### 2.5 `SAST_Tool_Development_Blueprint.md`

- 路径：[SAST_Tool_Development_Blueprint.md](file:///e:/chanzisast/SAST_Tool_Development_Blueprint.md)
- 内容形态：结构化 Markdown 文档（带小节、表格、代码块、Mermaid 图）。
- 主要内容块（按标题顺序）：
  - “系统架构概览”小节：列出组件选型表（Java 21+、JavaFX、Eclipse JDT、Neo4j Embedded、Lucene 等）。
  - “数据存储设计”小节：以 Tier 1/2/3 描述 `..._lspdata`、`..._lucene`、`..._neo4j` 三类目录用途。
  - “图模型设计”小节：列出节点类型（Class/Method/Arg）与关系（CALLS/HAS_METHOD/HAS_ARG/DATA_FLOW）。
  - “核心流水线”小节：按阶段描述预处理、ETL、检测执行规则（`.cypher`）的流程。
  - “开发起步建议”小节：给出从解析、入库、调用图构建、Cypher 查询验证的步骤建议。

### 2.6 `工具框架分析推导.md`

- 路径：[工具框架分析推导.md](file:///e:/chanzisast/%E5%B7%A5%E5%85%B7%E6%A1%86%E6%9E%B6%E5%88%86%E6%9E%90%E6%8E%A8%E5%AF%BC.md)
- 内容形态：包含“工具调用日志片段 + 分析报告正文”的 Markdown 文档。
- 文件开头：出现类似 `toolName: ... / status: ... / filePath: ...` 的交互/工具调用记录。
- 后续正文：出现“技术架构分析报告”标题、小节、表格与 Mermaid 图，内容涉及：
  - 从 `app/ChanziSAST.cfg`、`lsp/bin/jdtls`、依赖 jar 名称、日志路径等进行信息整理。
  - 以“阶段一/二/三”描述启动、LSP、ETL、规则执行的过程文字。
  - “关键库/文件指纹”表格：列出 `app/chanzi-*.jar`、`lsp/bin/jdtls` 等条目与作用说明。

### 2.7 `日志目录分析报告.md`

- 路径：[日志目录分析报告.md](file:///e:/chanzisast/%E6%97%A5%E5%BF%97%E7%9B%AE%E5%BD%95%E5%88%86%E6%9E%90%E6%8A%A5%E5%91%8A.md)
- 内容形态：同样包含“工具调用日志片段 + 报告正文”的 Markdown 文档。
- 正文主要内容块：
  - “数据目录解剖”表：描述 `..._lspdata`、`..._lucene`、`..._neo4j` 三类目录（对应 Eclipse workspace、Lucene 索引、Neo4j 数据）。
  - “图模型推测”与“流水线复盘”文字段落（含 Mermaid 图）。
  - 该文件引用并提及 `Hello-Java-Sec_neo4j_.../logs/debug.log`、`.../query.log` 等路径。

---

## 3. `logs\`（应用运行日志目录）

### 3.1 `logs/chanzisast.log`

- 路径：[chanzisast.log](file:///e:/chanzisast/logs/chanzisast.log)
- 内容形态：文本日志，每行包含时间戳、线程、级别、logger 名称、消息。
- 日志中可见的典型信息类型（仅按出现内容描述）：
  - 程序启动：`com.chanzi.ui.JavaFXBootStrap - starting....`
  - H2 数据库：出现“连接池初始化完成、Tasks 表已创建（新表）”等信息；并伴随 `taskInfo.trace.db` 记录的表不存在异常。
  - 任务与步骤：出现大量 `step X complete!`，以及“新增任务成功”“更新任务状态成功”等。
  - LSP 进程启动参数：日志中出现完整的 Java 命令行（含 `-javaagent:...\\lsp\\lspagent.jar`、`-jar ...\\org.eclipse.equinox.launcher_...jar`、`-configuration ...\\lsp\\config_win`、`-data ...\\Hello-Java-Sec_lspdata_...`）。
  - 规则加载：日志明确出现从 `chanzi-2025.4.1-ob.jar` 中加载内置规则资源目录 `rules`，并列出每一个 `.cypher` 规则的 entryName；同时记录“规则数量：122”。

#### 3.1.1 规则加载片段（含完整规则列表）

下述内容是 `chanzisast.log` 中关于规则加载的连续片段（包含每条规则的 `entryName` 与“加载规则”行，并包含最终“规则数量：122”汇总）：

见：[chanzisast.log:L75-L333](file:///e:/chanzisast/logs/chanzisast.log#L75-L333)

（该片段在日志中逐条出现的规则文件名形如 `com/chanzi/rules/<rule>.cypher`，共 122 条。）

#### 3.1.2 内置规则文件名清单（122 条）

该清单对应 `chanzi-2025.4.1-ob.jar` 内的资源路径：`/com/chanzi/rules/*.cypher`（文件名来自 `chanzisast.log` 的 `entryName:` 行；下方仅列出 `<rule>.cypher` 的文件名部分）。

```text
any_activiti_ssti.cypher
any_any_cmdi.cypher
any_any_ldapi.cypher
any_any_pathtraver.cypher
any_any_ssrf.cypher
any_any_upload.cypher
any_any_urlredirect.cypher
any_any_xss.cypher
any_any_xxe.cypher
any_BeanShell_codei.cypher
any_el_codei.cypher
any_fastjson_deserialization.cypher
any_freemarker_ssti.cypher
any_freemarker_xss.cypher
any_groovyshell_codei.cypher
any_hash2_weekhash.cypher
any_hash_weekhash.cypher
any_hessian_deserialization.cypher
any_java_deserialization.cypher
any_jdbctemplate_sqli.cypher
any_jdbc_sqli.cypher
any_jndi_jndii.cypher
any_jpa_sqli.cypher
any_jshell_codei.cypher
any_mvel_codei.cypher
any_mybatisplus_sqli.cypher
any_mybatis_sqli.cypher
any_ognl_codei.cypher
any_oss_upload.cypher
any_qlexpress_codei.cypher
any_reflect_codei.cypher
any_ScriptEngine_codei.cypher
any_snakeyaml_deserialization.cypher
any_socket_ssrf.cypher
any_spel_codei.cypher
any_thymeleaf_ssti.cypher
any_velocity_ssti.cypher
any_velocity_xss.cypher
any_XMLDecoder_deserialization.cypher
any_xstream_deserialization.cypher
asterisk_alloworigin_cors.cypher
config_actuator2_misconfig.cypher
config_actuator_misconfig.cypher
config_druid_misconfig.cypher
config_h2_misconfig.cypher
config_secret_hardcode.cypher
config_secret_weekpass.cypher
cookie_response_cookiesecure.cypher
exception_any_infoleak.cypher
id_jdbctemplate_hpe.cypher
id_jdbc_hpe.cypher
id_mybatis_hpe.cypher
id_otherdbquery_hpe.cypher
java_druid_misconfig.cypher
java_secret2_hardcode.cypher
java_secret2_weekpass.cypher
java_secret_hardcode.cypher
java_swagger_misconfig.cypher
jfinal_any_upload.cypher
jsp_any_xss.cypher
origin_alloworigin_cors.cypher
other_activiti_ssti.cypher
other_any_cmdi.cypher
other_any_ldapi.cypher
other_any_pathtraver.cypher
other_any_ssrf.cypher
other_any_urlredirect.cypher
other_any_xss.cypher
other_any_xxe.cypher
other_BeanShell_codei.cypher
other_el_codei.cypher
other_fastjson_deserialization.cypher
other_freemarker_ssti.cypher
other_freemarker_xss.cypher
other_groovyshell_codei.cypher
other_hash2_weekhash.cypher
other_hash_weekhash.cypher
other_java_deserialization.cypher
other_jdbctemplate_sqli.cypher
other_jdbc_sqli.cypher
other_jndi_jndii.cypher
other_jpa_sqli.cypher
other_jshell_codei.cypher
other_mvel_codei.cypher
other_mybatis_sqli.cypher
other_ognl_codei.cypher
other_oss_upload.cypher
other_qlexpress_codei.cypher
other_reflect_codei.cypher
other_ScriptEngine_codei.cypher
other_snakeyaml_deserialization.cypher
other_socket_ssrf.cypher
other_spel_codei.cypher
other_thymeleaf2_ssti.cypher
other_thymeleaf_ssti.cypher
other_velocity_ssti.cypher
other_velocity_xss.cypher
other_XMLDecoder_deserialization.cypher
other_xstream_deserialization.cypher
pom_dubbo_deserialization.cypher
pom_fastjson_deserialization.cypher
pom_jacksondatabind_deserialization.cypher
pom_jxpath_codei.cypher
pom_log4j_codei.cypher
pom_shiro_deserialization.cypher
pom_snakeyaml_deserialization.cypher
pom_springgateway_codei.cypher
pom_struts2_codei.cypher
pom_xstream_deserialization.cypher
pom_xxljob_codei.cypher
readobject_any_cmdi.cypher
socket_any_cmdi.cypher
socket_java_deserialization.cypher
spring_templet_xss.cypher
spring_thymeleaf_ssti.cypher
websocket_any_cmdi.cypher
websocket_any_deserialization.cypher
xml_druid_misconfig.cypher
xml_secret2_hardcode.cypher
xml_secret2_weekpass.cypher
xml_secret_hardcode.cypher
xml_secret_weekpass.cypher
```

---

## 4. `app\`（应用包内容：启动配置 + 依赖 JAR）

`app\` 目录中绝大多数为 `.jar` 依赖文件（第三方库与组件），另包含少量配置/元数据文件：

- `.package`
- `ChanziSAST.cfg`
- `arrow-bom-2025.01.0.pom`
- 大量 `*.jar`（包括 `chanzi-2025.4.1-ob.jar` 等）

### 4.1 `app/.package`

- 路径：[.package](file:///e:/chanzisast/app/.package)
- 内容：单行文本 `ChanziSAST`（可视为打包产物的包名/产品名标记）。

### 4.2 `app/ChanziSAST.cfg`

- 路径：[ChanziSAST.cfg](file:///e:/chanzisast/app/ChanziSAST.cfg)
- 内容形态：INI 风格配置；包含 `[Application]` 与 `[JavaOptions]` 两个 section。
- 行数：366 行

#### 4.2.1 `[Application]` 段

关键字段（示例）：
- `app.mainclass=com.chanzi.ui.JavaFXBootStrap`：主类（JavaFX 启动类）。
- 多条 `app.classpath=$APPDIR\*.jar`：显式枚举 classpath 依赖（包含核心业务 jar 与大量第三方库）。

文件开头可见：
- `app.classpath=$APPDIR\chanzi-2025.4.1-ob.jar`（核心 jar）
- `app.mainclass=com.chanzi.ui.JavaFXBootStrap`

文件末尾可见（示例摘录）：
- `app.classpath=$APPDIR\tomcat-util-scan-11.0.0-M21.jar`
- `app.classpath=$APPDIR\zstd-proxy-2025.01.0.jar`

#### 4.2.2 `[JavaOptions]` 段

当前可见的 Java options（示例）：
- `java-options=-Djpackage.app-version=25.4.1`

### 4.3 `app/arrow-bom-2025.01.0.pom`

- 路径：[arrow-bom-2025.01.0.pom](file:///e:/chanzisast/app/arrow-bom-2025.01.0.pom)
- 文件类型：Maven POM（packaging 为 `pom`）
- 可见信息：
  - `<parent>` 为 `org.neo4j:parent:2025.01.0`
  - `<arrow.version>` 为 `18.0.0`
  - `<dependencies>` 中列出 `org.apache.arrow:flight-core:${arrow.version}` 等，并包含若干 `<exclusions>`（文件内可见英文注释提到 netty http2 版本的安全问题，因此显式引入修复版本的依赖）

### 4.4 `app/*.jar`（依赖与核心逻辑包）

由于 `app\` 下 jar 数量非常多（在 `ChanziSAST.cfg` 中以 `app.classpath=` 形式逐行列出），这里按“可从文件名直接识别的组件类别”进行描述（仅基于文件名与日志中出现的类/包名，不展开 jar 内部 class 代码）：

- 核心业务 jar：
  - `chanzi-2025.4.1-ob.jar`：日志中出现 `jar:file:/E:/chanzisast/app/chanzi-2025.4.1-ob.jar!/com/chanzi/Loader.class`、并从其中加载 `com/chanzi/rules/*.cypher` 规则资源。
- GUI / JavaFX：
  - `javafx-*-24.0.2*.jar`（base/controls/fxml/graphics，含 win 变体 `*-win.jar`）
  - `atlantafx-base-2.0.1.jar`、`richtextfx-0.11.6.jar`、`reactfx-2.0-M5.jar`、`flowless-0.7.4.jar`、`undofx-2.1.1.jar`、`wellbehavedfx-0.3.3.jar`
- 图数据库 / Neo4j：
  - 大量 `neo4j-2025.01.0.jar` 与 `neo4j-*.jar`（如 kernel、dbms、cypher、procedure、server 等组件）
  - `cypher-*.jar`（Cypher 解析与相关组件）
- 文本索引 / Lucene：
  - `lucene-core-9.11.0.jar`、`lucene-queryparser-9.11.1.jar`、`lucene-analysis-common-9.11.1.jar`、`lucene-backward-codecs-9.11.1.jar`
- Eclipse/IDE 相关（Java 解析与 Git/构建工具链）：
  - `org.eclipse.jdt.core-*.jar`、`org.eclipse.lsp4j-*.jar`、`org.eclipse.jgit-*.jar` 等
- 内置 Web 容器/HTTP 组件（文件名可见 Jetty/Tomcat/Jersey 等）：
  - `jetty-*.jar`、`tomcat-*.jar`、`jersey-*.jar`、`httpclient/httpcore` 等
- 认证/安全相关库（文件名可见）：
  - `shiro-*.jar`、`jjwt-*.jar`、`snakeyaml-2.3.jar` 等
- 数据库：
  - `h2-2.3.232.jar`、连接池 `HikariCP-7.0.1.jar`
- 其他常见基础库：
  - `gson-2.13.2.jar`、`guava-32.1.3-android.jar`、`commons-*`、`jackson-*`、`netty-*`、`protobuf-*`、`grpc-*` 等

---

## 5. `lsp\`（内置 Eclipse JDT Language Server 相关文件）

`lsp\` 目录用于提供 Java 代码解析/符号索引能力（从目录结构与文件命名可见为 JDTLS 的一套分发包），包含启动脚本、跨平台配置目录、插件 jar、features 等。

### 5.1 `lsp/bin/`（启动脚本）

#### 5.1.1 `lsp/bin/jdtls`（Python 引导脚本）

- 路径：[jdtls](file:///e:/chanzisast/lsp/bin/jdtls)
- 内容：`#!/usr/bin/env python3` 的 Python 启动器，动态加载同目录的 `jdtls.py` 并执行 `jdtls.main(sys.argv[1:])`。

#### 5.1.2 `lsp/bin/jdtls.py`（主启动逻辑）

- 路径：[jdtls.py](file:///e:/chanzisast/lsp/bin/jdtls.py)
- 文件头部：包含 Eclipse Public License 2.0 版权声明与作者信息。
- 主要函数与行为（按代码可见内容描述）：
  - `get_java_executable(known_args)`：根据 `--java-executable` 参数或 `JAVA_HOME` 环境变量选择 Java 路径；可选校验 Java 主版本号，低于 21 时抛异常（字符串为 `jdtls requires at least Java 21`）。
  - `find_equinox_launcher(jdtls_base_directory)`：在 `plugins/` 目录中查找 `org.eclipse.equinox.launcher*.jar`。
  - `get_shared_config_path(jdtls_base_path)`：根据平台选择 `config_linux/config_mac/config_win`。
  - `main(args)`：构造 JDTLS 启动参数（例如 `-Declipse.application=org.eclipse.jdt.ls.core.id1`、`-Dosgi.*`、`--add-modules=ALL-SYSTEM`、`--add-opens ...`、`-jar <launcher>`、`-data <workspace>` 等），在 POSIX 下用 `os.execvp` 替换进程，在 Windows 下 `subprocess.run` 启动。

#### 5.1.3 `lsp/bin/jdtls.bat`（Windows 批处理）

- 路径：[jdtls.bat](file:///e:/chanzisast/lsp/bin/jdtls.bat)
- 内容：调用 `python %~dp0/jdtls %*` 并 `pause`。

### 5.2 `lsp/config_*`（跨平台配置目录）

可见目录：
- `config_win/`、`config_linux/`、`config_mac/` 及其 `*_arm` 变体
- `config_ss_win/`、`config_ss_linux/`、`config_ss_mac/` 及其 `*_arm` 变体

其中每个目录通常包含一个 `config.ini`（Eclipse/OSGi 配置文件），例如：
- [config_win/config.ini](file:///e:/chanzisast/lsp/config_win/config.ini)
- [config_linux/config.ini](file:///e:/chanzisast/lsp/config_linux/config.ini)

`config.ini` 中可见的字段形态：
- `eclipse.application=org.eclipse.jdt.ls.core.id1`
- `eclipse.product=org.eclipse.jdt.ls.core.product`
- `osgi.bundles=reference:file:...jar@...`（以逗号分隔列出大量 bundle jar）
- `osgi.framework=file:plugins/org.eclipse.osgi_...jar`
- `osgi.framework.extensions=reference:file:...jar`

`config_win/` 目录中还包含若干 OSGi 运行时缓存/元数据文件夹（例如 `org.eclipse.core.runtime/`、`org.eclipse.osgi/`、以及 `org.eclipse.equinox.launcher/` 下的 `eclipse_*.dll`）。

### 5.3 `lsp/plugins/`（JDTLS 插件 jar 列表）

- 路径：[lsp/plugins](file:///e:/chanzisast/lsp/plugins)
- 内容：大量以 `org.eclipse.*`、`org.apache.*`、`com.google.*`、`jakarta.*`、`org.osgi.*` 等命名的 jar，供 OSGi/JDTLS 启动加载。
- 该目录文件名清单可直接查看：[lsp/plugins](file:///e:/chanzisast/lsp/plugins)（目录列出了所有插件 jar 文件名）。

### 5.4 `lsp/features/`

- 路径：[lsp/features](file:///e:/chanzisast/lsp/features)
- 内容：目前可见一个 jar：`org.eclipse.equinox.executable_3.8.2900.v20250331-1702.jar`

### 5.5 `lsp/lspagent.jar`

- 路径：[lspagent.jar](file:///e:/chanzisast/lsp/lspagent.jar)
- 类型：Jar（Java Agent）
- 日志关联：`chanzisast.log` 中启动 LSP 时出现参数 `-javaagent:E:\chanzisast\lsp\lspagent.jar`。

---

## 6. `runtime\`（内置 Java Runtime）

`runtime\` 目录是随应用一起分发的 Java 运行环境（包含 `bin/`、`conf/`、`lib/`、`legal/` 等标准结构）。

### 6.1 `runtime/release`

- 路径：[release](file:///e:/chanzisast/runtime/release)
- 内容：文本键值对，主要包含：
  - `JAVA_VERSION="24.0.1"`
  - `MODULES="..."`：列出该 runtime 内置的 Java 模块列表（如 `java.base`、`java.desktop`、`java.net.http`、`jdk.jpackage`、`jdk.jshell` 等）。

### 6.2 `runtime/bin/`

- 目录中包含大量标准 JDK 可执行文件与动态库（在顶层枚举中可见 `java.exe`、`javac.exe`、`jar.exe`、`jpackage.exe`、`keytool.exe` 等，以及大量 `*.dll`）。
- 该目录也包含 `server/jvm.dll` 等 JVM 相关文件（见目录列表）。

### 6.3 `runtime/conf/`

可见配置文件包括（按目录列出）：
- `conf/management/`：`jmxremote.access`、`jmxremote.password.template`、`management.properties`
- `conf/security/`：`java.security` 与 `policy/limited|unlimited` 下的策略文件，以及 `policy/README.txt`
- 其他：`jaxp.properties`、`logging.properties`、`net.properties`、`sound.properties`、`jaxp-strict.properties.template`

### 6.4 `runtime/lib/`

可见文件包括：
- `modules`（Java 模块镜像文件）
- `cacerts`（证书库）、`blocked.certs`、`public_suffix_list.dat`
- `classlist`、`ct.sym`、`jvm.cfg`、`tzdb.dat`、`jfr/default.jfc` 等

### 6.5 `runtime/legal/`

该目录包含按模块划分的第三方许可信息与版权文件（大量 `COPYRIGHT`、`LICENSE`、以及 `*.md` 说明文件），例如：
- `runtime/legal/java.base/*.md`（aes、asm、icu、unicode、zlib 等）
- `runtime/legal/java.desktop/*.md`（freetype、jpeg、libpng 等）
- `runtime/legal/jdk.javadoc/*.md`（jquery、dejavufonts 等）

---

## 7. `Hello-Java-Sec_*`（运行过程中生成的数据/索引目录示例）

该工具目录下包含一组以 `Hello-Java-Sec_*_20251211090724` 命名的目录，看起来是一次分析任务/样例项目运行后生成的工件（分别对应 workspace、全文索引、图数据库）。

### 7.1 `Hello-Java-Sec_lspdata_20251211090724\`

- 路径：[Hello-Java-Sec_lspdata_20251211090724](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724)
- 目录结构特征：以 `.metadata/.plugins/...` 为核心，符合 Eclipse Workspace 的布局；内部含多个 Eclipse 插件的状态文件、prefs、历史记录等。

#### 7.1.1 代表性文件内容（举例）

- `.metadata/.log`  
  路径：[.log](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724/.metadata/.log)  
  内容形态：Eclipse/JDTLS 的会话日志（`!SESSION`、`!ENTRY`、`!MESSAGE` 记录）。可见信息包括：
  - Java 版本：`java.version=24.0.1`（同时记录 `java.vendor=Oracle Corporation`）
  - 启动参数：`Command-line arguments:  -data C:\Users\...\Hello-Java-Sec_lspdata_...`
  - JDTLS 初始化：`Initializing Java Language Server 1.46.1.202504011455`
  - Workspace folders、Maven 项目导入与 resolved classpath（内容中列出 `org.eclipse.m2e.MAVEN2_CLASSPATH_CONTAINER` 下的大量 `~/.m2` 依赖条目）

- `.metadata/.plugins/org.eclipse.jdt.launching/.install.xml`  
  路径：[.install.xml](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724/.metadata/.plugins/org.eclipse.jdt.launching/.install.xml)  
  内容：记录 JDK 安装目录与时间戳，例如：
  - `D:\jdk-22.0.2`
  - `E:\chanzisast\runtime`

- `.metadata/.plugins/org.eclipse.jdt.launching/libraryInfos.xml`  
  路径：[libraryInfos.xml](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724/.metadata/.plugins/org.eclipse.jdt.launching/libraryInfos.xml)  
  内容：记录 JDK home 与版本，例如：
  - `home="D:\jdk-22.0.2" version="22.0.2"`
  - `home="E:\chanzisast\runtime" version="24.0.1"`

- `.metadata/.plugins/org.eclipse.buildship.core/gradle/versions.json`  
  路径：[versions.json](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724/.metadata/.plugins/org.eclipse.buildship.core/gradle/versions.json)  
  内容：Gradle 版本列表 JSON（包含 nightly/snapshot/rc 等版本的 downloadUrl、checksum 等字段）。

- `.metadata/.plugins/org.eclipse.m2e.core/workspacestate.properties`  
  路径：[workspacestate.properties](file:///e:/chanzisast/Hello-Java-Sec_lspdata_20251211090724/.metadata/.plugins/org.eclipse.m2e.core/workspacestate.properties)  
  内容：将 Maven 坐标映射到本地工程路径（示例含 `com.best:javasec` 的 `target/classes`、`pom.xml` 等）。

### 7.2 `Hello-Java-Sec_lucene_20251211090724\`

- 路径：[Hello-Java-Sec_lucene_20251211090724](file:///e:/chanzisast/Hello-Java-Sec_lucene_20251211090724)
- 文件清单（目录内全部可见）：
  - `_0.cfe`、`_0.cfs`、`_0.si`、`segments_1`、`write.lock`
- 内容形态：二进制索引文件（Lucene 标准段文件命名风格），用于保存全文索引数据。

### 7.3 `Hello-Java-Sec_neo4j_20251211090724\`

- 路径：[Hello-Java-Sec_neo4j_20251211090724](file:///e:/chanzisast/Hello-Java-Sec_neo4j_20251211090724)
- 目录结构：
  - `data/`：Neo4j 数据文件（`databases/neo4j` 与 `databases/system` 两个库；以及 `transactions/` 事务日志）
  - `logs/`：Neo4j 日志（`debug.log`、`http.log`、`query.log`、`security.log`）

#### 7.3.1 `data/` 中可见的典型文件

在 `data/databases/neo4j/` 与 `data/databases/system/` 下可见大量以 `neostore*` 命名的文件，例如：
- `neostore`
- `neostore.nodestore.db`、`neostore.relationshipstore.db`
- `neostore.propertystore.db`（及 `.arrays`、`.strings` 等变体）
- `neostore.labeltokenstore.db`、`neostore.relationshiptypestore.db`（及 `.names` 等）
- `schema/index/.../index-*`（schema/index 子目录下的索引文件）

这些文件为 Neo4j 在磁盘上的存储文件（均为二进制）。

#### 7.3.2 `logs/debug.log`

- 路径：[debug.log](file:///e:/chanzisast/Hello-Java-Sec_neo4j_20251211090724/logs/debug.log)
- 内容形态：逐行 JSON 日志（字段如 `time`、`level`、`category`、`message`）。
- 日志中可见的内容类别（举例）：
  - “Logging config in use: Embedded default config ...”
  - Java 版本告警、heap/pagecache 配置告警
  - 系统诊断信息（物理内存、JVM 内存、OS 信息、classpath 列表、系统属性等）
  - DBMS config（含 `server.directories.neo4j_home=...Hello-Java-Sec_neo4j_...`）
  - 数据库创建与 checkpoint 信息（system/neo4j 两个库）

#### 7.3.3 `logs/query.log` / `logs/http.log` / `logs/security.log`

- 路径：
  - [query.log](file:///e:/chanzisast/Hello-Java-Sec_neo4j_20251211090724/logs/query.log)
  - [http.log](file:///e:/chanzisast/Hello-Java-Sec_neo4j_20251211090724/logs/http.log)
  - [security.log](file:///e:/chanzisast/Hello-Java-Sec_neo4j_20251211090724/logs/security.log)
- 当前文件状态：这三个文件在本目录中存在，但读取时显示为空文件（0 行）。

---

## 8. 附：目录展开清单（关键目录）

### 8.1 `app\`（非 jar 文件）

该目录非 jar 文件清单如下：
- [app/.package](file:///e:/chanzisast/app/.package)
- [app/ChanziSAST.cfg](file:///e:/chanzisast/app/ChanziSAST.cfg)
- [app/arrow-bom-2025.01.0.pom](file:///e:/chanzisast/app/arrow-bom-2025.01.0.pom)

### 8.2 `lsp\`（不含 plugins jar 的目录结构摘要）

见：[lsp 目录树](file:///e:/chanzisast/lsp)

### 8.3 `runtime\`（不含大量可执行文件的目录结构摘要）

见：[runtime 目录树](file:///e:/chanzisast/runtime)

