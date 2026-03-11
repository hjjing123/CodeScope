MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
sinkNode.name = 'spring.h2.console.settings.web-allow-others' AND
sinkNode.value = 'true'

RETURN
  sinkNode AS path
/*
Chanzi-Separator

H2 Database Console 未授权访问漏洞

该漏洞主要指的是 H2 数据库控制台的远程代码执行漏洞（CVE-2021-42392）。这个漏洞允许攻击者在未经过身份验证的情况下执行任意代码。以下是该漏洞的详细介绍和修复方案：

漏洞描述：

H2 Database Console 提供了一个基于 Web 的管理界面，用于管理 H2 数据库。在某些配置下，这个控制台可以被远程访问。如果配置不当，攻击者可以利用这一点执行远程代码。这个漏洞与 Log4j 的 Log4Shell（CVE-2021-44228）漏洞有相似之处，因为它们都涉及到 JNDI（Java Naming and Directory Interface）远程类加载的问题。

产生原因：

在 H2 Database 的某些版本中，如果配置了以下选项，就会允许外部用户访问 Web 管理页面，且没有进行身份验证：

properties
spring.h2.console.enabled=true
spring.h2.console.settings.web-allow-others=true

这使得攻击者可以利用控制台执行恶意操作，包括但不限于 JNDI 注入攻击。

影响范围：

受影响的 H2 Database 版本包括：1.1.100 至 2.0.204

Chanzi-Separator

升级 H2 Database：官方已经发布了修复补丁，建议用户升级到 H2 Database 版本 2.0.206 或更高版本。

更改配置：如果暂时无法升级，可以更改应用配置，不要设置 spring.h2.console.settings.web-allow-others=true，以防止远程未授权访问。

使用白名单：如果 H2 控制台必须暴露给外部，应使用 IP 白名单限制访问。

安全约束：在 Web 服务器上部署 H2 控制台时，可以添加安全约束，仅允许特定用户访问控制台页面。

Chanzi-Separator
*/