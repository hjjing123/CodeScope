// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.apache.dubbo' AND   sinkNode.artifactId = 'dubbo' AND
  (sinkNode.realVersion STARTS WITH '2.5' OR
  sinkNode.realVersion STARTS WITH '2.6' OR
  sinkNode.realVersion STARTS WITH '2.7' OR
  sinkNode.realVersion STARTS WITH '3.1' )
RETURN
  sinkNode AS path

/*
Chanzi-Separator

dubbo反序列化漏洞

Apache Dubbo 是一个由阿里巴巴开源的高性能、轻量级的开源分布式服务框架，它提供了服务发现、流量治理、可观测、认证鉴权等能力。然而，像所有软件一样，Dubbo 也存在一些已知的安全漏洞。以下是一些 Dubbo 的已知漏洞：

CVE-2019-17564（严重）：这是一个反序列化漏洞，允许攻击者在特定条件下执行任意代码。受影响的版本包括 Dubbo 2.7.0 至 2.7.4 和 2.6.0 至 2.6.7，以及 2.5.x 的所有版本。官方已经发布了修复补丁，并建议用户升级到安全版本。

CVE-2021-29441：这是 Nacos 的一个权限认证绕过漏洞，但由于 Nacos 常与 Dubbo 一起使用，这个漏洞也可能影响 Dubbo 用户。受影响的版本包括 Nacos 1.4.1 之前的版本。修复建议包括升级 Nacos 版本和开启鉴权功能。

CVE-2021-30179：这个漏洞与 Dubbo 的泛化调用处理有关，可以导致远程代码执行。受影响的版本包括 Dubbo 2.7.x、3.0.x 和 3.1.x 的某些版本。官方已经发布了修复版本。

CVE-2021-36162：这个漏洞与 YAML 反序列化有关，可以导致远程代码执行。受影响的版本包括 Dubbo 2.7.0 至 2.7.12 和 3.0.0 至 3.0.1。官方建议用户升级到指定版本。

CVE-2021-32824：这是一个 Telnet handler 远程代码执行漏洞。受影响的版本包括 Dubbo 2.5.x、2.6.10 之前版本和 2.7.10 之前版本。官方建议用户升级 Dubbo 版本或配置参数以规避该漏洞。

CVE-2021-44228（Log4j）：虽然这个漏洞主要影响 Log4j，但由于 Dubbo 可能依赖 Log4j，因此也间接受到影响。Dubbo 本身不强依赖 Log4j，也不会通过依赖传递将 Log4j 带到业务工程中去，但使用 Dubbo 的用户可能需要检查并升级 Log4j 依赖。

CVE-2022-22965：这是一个 Spring Framework 的远程代码执行漏洞，由于 Dubbo 可能作为 Spring 生态系统的一部分使用，因此也可能受到此漏洞的影响。这个漏洞允许攻击者在 JDK 9+ 版本上通过数据绑定执行远程代码。

CVE-2023-29234：这是一个反序列化漏洞，允许攻击者通过向 Dubbo 服务发送特制的序列化对象来利用此漏洞。受影响的版本包括 Dubbo 3.1.0-3.1.10 和 3.2.0-3.2.4。

对于这些漏洞，官方已经发布了相应的修复版本和安全建议。用户应尽快升级到安全版本，并采取相应的安全措施来保护系统。如果需要更详细的信息，可以访问 Dubbo 的官方文档和安全通告页面。

Chanzi-Separator

Apache Dubbo 相关的漏洞及其修复方案如下，因涉及漏洞较多，我们通常建议升级到最新的稳定版本：

CVE-2019-17564：这是一个反序列化漏洞，影响 Apache Dubbo 2.7.0 至 2.7.4 和 2.6.0 至 2.6.7，以及 2.5.x 的所有版本。攻击者可以利用该漏洞执行任意代码。修复方案是升级到 Apache Dubbo 2.7.5 或更高版本 。

CVE-2021-29441：这是 Nacos 的一个权限认证绕过漏洞，但由于 Nacos 常与 Dubbo 一起使用，这个漏洞也可能影响 Dubbo 用户。受影响的版本包括 Nacos 1.4.1 之前的版本。修复方案包括升级 Nacos 版本和开启鉴权功能 。

CVE-2021-30179：这是一个远程代码执行漏洞，影响 Apache Dubbo 2.7.0 至 2.7.9 和 2.6.0 至 2.6.9。攻击者可以通过控制反序列化的方式执行任意代码。修复方案是升级到 Apache Dubbo 2.7.10 或更高版本 。

CVE-2021-32824：这是一个 Telnet handler 远程代码执行漏洞。受影响的版本包括 Dubbo 2.5.x、2.6.10 之前版本和 2.7.10 之前版本。修复方案包括升级 Dubbo 版本或配置参数以规避该漏洞 。

CVE-2023-29234：这是一个反序列化漏洞，影响 Apache Dubbo 3.1.0 至 3.1.10 和 3.2.0 至 3.2.4。攻击者可以通过向 Dubbo 服务发送特制的序列化对象来利用此漏洞。修复方案是升级 Apache Dubbo 至对应安全版本 。

CVE-2022-22965：这是一个 Spring Framework 的远程代码执行漏洞，由于 Dubbo 可能作为 Spring 生态系统的一部分使用，因此也可能受到此漏洞的影响。修复方案是升级 Spring Framework 到安全版本，如 5.3.18 或 5.2.20 。

CVE-2021-44228（Log4j）：虽然这个漏洞主要影响 Log4j，但由于 Dubbo 可能依赖 Log4j，因此也间接受到影响。修复方案是升级 Log4j 到安全版本，如 2.17.1 。

对于这些漏洞，官方已经发布了相应的修复版本和安全建议。用户应尽快升级到安全版本，并采取相应的安全措施来保护系统。如果需要更详细的信息，可以访问 Dubbo 的官方文档和安全通告页面 。

Chanzi-Separator
*/