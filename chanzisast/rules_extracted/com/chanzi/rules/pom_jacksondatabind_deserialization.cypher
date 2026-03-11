// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'com.fasterxml.jackson.core' AND   sinkNode.artifactId = 'jackson-databind' AND
  sinkNode.realVersion =~ '2\\.(0|1|2|3|4|5|6|7|8|9|10|11|12).*'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

Jackson反序列化漏洞

Jackson-databind 是一个流行的 Java JSON 处理库，它提供了序列化和反序列化的功能。

CVE-2017-7525 是一个严重的安全漏洞，影响了 FasterXML Jackson-databind 库的多个版本。这个库是 Java 语言中用于序列化和反序列化 JSON 数据的流行工具。该漏洞允许未经身份验证的攻击者通过向 ObjectMapper 的 readValue 方法发送恶意构造的输入来执行代码。

漏洞原理：
Jackson-databind 支持多态反序列化，这意味着如果在 JSON 数据中指定了具体的类信息，Jackson 将会尝试创建并初始化该类的实例。攻击者可以利用这一点，通过构造包含恶意类信息的 JSON 数据来实现远程代码执行。例如，攻击者可以指定一个类，该类在初始化时会执行远程下载并执行代码的操作。

影响范围：

FasterXML Jackson-databind < 2.6.7.1
FasterXML Jackson-databind < 2.7.9.1
FasterXML Jackson-databind < 2.8.9

然而，它也存在一些安全漏洞，主要包括：

CVE-2017-7525（严重）：这是一个反序列化漏洞，允许攻击者通过构造恶意的 JSON 数据来执行任意代码。受影响的版本包括 FasterXML Jackson-databind < 2.6.7.1、< 2.7.9.1 和 < 2.8.9。修复方案是升级到安全版本
。

CVE-2019-12384：这个漏洞与 JDK 11 及以上版本中的模块系统有关，可以通过 Jackson-databind 进行利用。攻击者可以利用这个漏洞绕过安全限制，执行任意代码
。

CVE-2020-24616：这个漏洞影响了 FasterXML jackson-databind < 2.9.10.6 的版本。攻击者可以利用这个漏洞进行远程代码执行
。

CVE-2020-36179 至 CVE-2020-36189：这是一系列反序列化漏洞，影响了 FasterXML jackson-databind < 2.9.10.8 的版本。这些漏洞允许攻击者通过发送特制的 JSON 数据来执行任意代码
。

CVE-2020-8840：这是一个 JNDI 注入漏洞，影响了 FasterXML jackson-databind <= 2.9.10.2 的版本。攻击者可以利用这个漏洞执行远程代码
。

CVE-2020-35490 和 CVE-2020-35491：这些漏洞影响了 FasterXML jackson-databind < 2.9.10.8 的版本，允许攻击者通过反序列化执行远程代码执行
。

CVE-2020-36186 和 CVE-2020-36189：这些漏洞涉及 com.newrelic.agent.deps.ch.qos.logback.core.db 类，允许攻击者通过反序列化执行远程代码
。

CVE-2023-29234：这是一个反序列化漏洞，影响了 Apache Dubbo 使用的 Jackson-databind 库。攻击者可以利用这个漏洞执行任意代码
。
Chanzi-Separator

Jackson-databind 库中存在多个安全漏洞，以下是一些主要的漏洞及其修复方案，因涉及漏洞较多，我们通常建议升级到最新的稳定版本：

CVE-2017-7525：

影响版本：FasterXML Jackson-databind < 2.6.7.1、< 2.7.9.1 和 < 2.8.9。
修复方案：升级到 2.6.7.1、2.7.9.1 或 2.8.9 及以上版本。同时，避免使用 enableDefaultTyping() 方法，或者使用 enableDefaultTyping(ObjectMapper.DefaultTyping.NON_FINAL, JsonTypeInfo.As.PROPERTY) 并限制可接受的类类型。
CVE-2019-12384：

影响版本：Jackson-databind 2.X < 2.9.9.1。
修复方案：升级到 2.9.9.1 或更高版本。同时，确保应用程序中没有调用 enableDefaultTyping() 方法。
CVE-2020-24616：

影响版本：jackson-databind < 2.9.10.6。
修复方案：升级到 2.9.10.6 或更高版本。这个版本修复了多个反序列化漏洞，包括 br.com.anteros:Anteros-DBCP 组件库的不安全反序列化问题。
CVE-2020-36179 至 CVE-2020-36189：

影响版本：jackson-databind 2.x < 2.9.10.8。
修复方案：升级到 2.9.10.8 或更高版本。这些漏洞涉及多个组件库的不安全反序列化问题，包括 org.apache.commons.dbcp.cpdsadapter.DriverAdapterCPDS 等。
CVE-2020-36186 和 CVE-2020-36189：

影响版本：Jackson-databind < 2.9.10.7。
修复方案：升级到 2.9.10.7 或更高版本。这些漏洞涉及 org.apache.tomcat.dbcp.dbcp.datasources.PerUserPoolDataSource 和 com.newrelic.agent.deps.ch.qos.logback.core.db.DriverManagerConnectionSource 类的不安全反序列化问题。
CVE-2020-36179：

影响版本：Jackson-databind < 2.9.10.7。
修复方案：升级到 2.9.10.7 或更高版本。这个漏洞涉及 com.newrelic.agent.deps.ch.qos.logback.core.db.DriverManagerConnectionSource 类的不安全反序列化问题，可能导致 SSRF 和 RCE。

Chanzi-Separator
*/