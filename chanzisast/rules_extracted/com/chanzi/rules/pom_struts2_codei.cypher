// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.apache.struts' AND   sinkNode.artifactId = 'struts2-core' AND sinkNode.realVersion STARTS WITH '2.'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

Struts2远程代码执行漏洞

Apache Struts2 是一个流行的 Java Web 应用框架，它基于 MVC 设计模式。Struts2 的多个版本中存在安全漏洞，其中一些漏洞允许攻击者执行远程代码。以下是一些 Struts2 漏洞的基本原理和修复方案：

    S2-045：这个漏洞（CVE-2017-5638）允许攻击者通过修改 HTTP 请求头中的 Content-Type 来执行任意代码。漏洞的成因是在处理文件上传时，Struts2 的 Jakarta Multipart 解析器没有正确处理恶意构造的 Content-Type 值，导致 OGNL 表达式被执行。

    S2-048：这个漏洞允许攻击者通过 Struts1 插件在 Struts2 应用中执行任意命令。漏洞的成因是 Struts2 的 Struts1 插件在处理 ActionMessage 时，没有正确处理用户可控的输入，导致 OGNL 表达式注入。

    S2-052：这个漏洞（CVE-2017-9791）影响 Struts2 REST 插件的 XStream 组件，允许攻击者通过 XML 格式的数据包进行反序列化操作，从而执行任意代码。

    S2-053：这个漏洞允许攻击者在使用 Freemarker 模板引擎时，通过 OGNL 表达式执行任意命令。漏洞的成因是 Struts2 允许解析 OGNL 表达式，而 Freemarker 模板引擎在处理用户输入时没有足够的安全限制。

    S2-057：这个漏洞（CVE-2018-11776）允许攻击者通过 URL 参数中的 OGNL 表达式执行任意代码。漏洞的成因是 Struts2 的 DefaultActionMapper 类在处理带有重定向前缀的参数时，没有正确过滤恶意表达式。

Chanzi-Separator

Struts2 漏洞的修复建议通常包括以下几个步骤：

    升级 Struts2 版本：始终推荐将 Struts2 框架升级到最新的安全版本。例如，对于 S2-045 漏洞，应升级到 2.3.31 以上的版本，而对于 S2-048 漏洞，应升级到 2.3.29 以上的版本。这样可以确保大多数已知漏洞已被修复。

    修改配置：对于某些漏洞，可以通过修改 Struts2 的配置来增加安全性。例如，可以设置 struts.devMode 为 false 来关闭开发模式，这可以避免一些与开发模式相关的漏洞。

    代码审查和修改：在某些情况下，可能需要对源码进行审查和修改，以确保没有安全漏洞。例如，可以修改 DefaultActionMapper 类中的 handleSpecialParameters 方法，以防止恶意 URL 参数的解析。

    严格的输入验证：确保所有的用户输入都经过适当的验证和清理，避免直接将用户输入用于 OGNL 表达式或其他可能被恶意利用的上下文中。

    使用 Web 应用防火墙：作为额外的安全层，可以使用 Web 应用防火墙（WAF）来帮助检测和阻止针对已知漏洞的攻击。

    采用其他框架替代：目前 spring 等框架是更加主流的开发框架，安全性也相对较好，可以考虑采用 spring 等替代 struts2，另外即便采用 spring 等框架也需要及时升级到安全的版本。

请注意，具体的修复步骤可能会根据漏洞的不同而有所变化，因此建议参考官方的安全公告和文档，以及专业的安全顾问的建议来实施修复。同时，保持对 Struts2 相关安全动态的关注，以便及时采取必要的安全措施。
Chanzi-Separator
*/