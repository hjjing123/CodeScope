// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.apache.shiro' AND   sinkNode.artifactId = 'shiro-core' AND   sinkNode.realVersion =~ '1\\.(1|2|3|4|5|6|7|8|9|1[0-1]|12)\\..*'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

shiro反序列化漏洞

Apache Shiro 是一个广泛使用的 Java 安全框架，它提供了认证、授权、加密和会话管理等功能。然而，Shiro 也存在一些安全漏洞，其中最著名的是反序列化漏洞，尤其是 Shiro-550（CVE-2016-4437）和 Shiro-721（CVE-2019-12422）。

Shiro-550（CVE-2016-4437）漏洞原理：

    Shiro 在用户登录时提供了一个 "Remember Me" 功能，如果用户选择了这个选项，Shiro 会生成一个加密的 Cookie 来记住用户。
    这个 Cookie 的值是使用 AES 加密算法加密的，并且密钥是硬编码在 Shiro 的源码中。这意味着任何人都可以获取这个密钥并解密 Cookie。
    攻击者可以利用这个密钥构造一个恶意的序列化对象，然后将其作为 Cookie 发送给服务器。当服务器反序列化这个对象时，就会执行攻击者指定的代码。

Shiro-721（CVE-2019-12422）漏洞原理：

    这个漏洞与 Shiro-550 类似，但是它不需要知道 AES 加密的密钥。这是因为攻击者可以利用 Padding Oracle 攻击来构造恶意的 Cookie。
    Padding Oracle 攻击是一种利用加密算法的填充机制来解密数据的攻击方式。攻击者可以通过观察解密过程中的错误信息来推断出加密数据的内容。
    在 Shiro-721 中，攻击者可以发送特制的请求来观察服务器的响应，从而逐步构建出可以反序列化的恶意对象。

Chanzi-Separator

Apache Shiro 漏洞的修复方案主要针对其反序列化漏洞，尤其是 CVE-2016-4437（Shiro-550）和 CVE-2019-12422（Shiro-721）。以下是一些推荐的修复措施：

    升级 Shiro 版本：将 Shiro 框架升级到最新的安全版本，例如 1.7.1 或更高。新版本中默认使用随机生成的密钥，而不是硬编码的密钥，这增加了安全性。

    修改默认密钥：如果不便于升级 Shiro 版本，可以修改 rememberMe 功能的默认密钥。应该生成一个强密钥，并确保它不会被泄露。可以通过编程方式动态生成密钥，例如使用 org.apache.shiro.crypto.AbstractSymmetricCipherService#generateNewKey(int) 方法。

    禁用 rememberMe 功能：如果 rememberMe 功能不是必需的，可以考虑完全禁用它，以避免相关的安全风险。

    使用安全的序列化机制：确保应用程序使用的序列化机制是安全的，并且不容易受到反序列化攻击。

    监控和过滤输入：加强对所有用户输入的监控和过滤，确保不会处理恶意构造的数据。

    使用 Web 应用防火墙（WAF）：部署 WAF 可以帮助检测和阻止针对已知漏洞的攻击。

    密钥管理：确保密钥的安全存储和管理，避免将密钥硬编码在代码中。

Chanzi-Separator
*/