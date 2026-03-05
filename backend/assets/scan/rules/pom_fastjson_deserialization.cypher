// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'com.alibaba' AND   sinkNode.artifactId = 'fastjson' AND   sinkNode.realVersion < '1.2.83'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

fastjson反序列化漏洞

Fastjson反序列化漏洞的基本原理涉及到了Java的反射机制以及Fastjson库在处理JSON字符串到Java对象转换过程中的安全缺陷。以下是Fastjson反序列化漏洞的基本原理：

Fastjson的作用：Fastjson是阿里巴巴开源的Java库，用于将Java对象转换成JSON格式，以及将JSON字符串转换为Java对象。这个过程分别称为序列化和反序列化。

漏洞触发条件：当Fastjson库在反序列化过程中，如果配置允许自动类型识别（autoType），而没有适当的限制，攻击者可以构造特殊的JSON字符串来指定恶意类。

@type关键字：Fastjson允许在JSON字符串中使用@type关键字来指示目标对象的类型。这意味着，如果应用程序配置不当，攻击者可以利用@type指定恶意类，从而在反序列化过程中加载并执行恶意代码。

漏洞影响版本：Fastjson 1.2.24及之前版本容易受到此类漏洞的影响。

漏洞利用：攻击者可以利用Fastjson的autoType功能，通过构造含有@type的JSON字符串，触发恶意类的加载和执行，导致远程代码执行（RCE）漏洞。

漏洞修复：在Fastjson 1.2.25版本之后，引入了黑白名单机制来限制可以反序列化的类。但是，后续版本中仍然存在绕过黑白名单的漏洞，例如通过特定的类加载技巧或利用Fastjson的内部机制。

安全建议：为了防范Fastjson反序列化漏洞，建议开发者及时更新Fastjson到最新版本，并且在使用时关闭autoType功能或严格限制可接受的类型。同时，代码审计和安全测试也是必要的安全措施。

漏洞检测：可以使用自动化工具如xray进行漏洞检测，通过配置反连平台来检测Fastjson是否容易受到XXE攻击。

漏洞复现：在已知受影响的环境中，可以通过发送构造好的JSON字符串来复现漏洞，验证其存在性。

JNDI注入：Fastjson反序列化漏洞可以与JNDI注入相结合，利用远程或本地上下文来执行恶意代码。

请注意，尽管Fastjson开发者已经在后续版本中尝试修复这些漏洞，但新的绕过技巧和变种漏洞仍然不断被发现。因此，开发者需要持续关注Fastjson的安全更新，并采取适当的安全措施来保护应用程序。

Chanzi-Separator

Fastjson反序列化漏洞的修复建议主要包括以下几点：

    升级Fastjson版本：将Fastjson库升级到最新版本，例如1.2.83版本，这个版本修复了已知的安全漏洞，并引入了autotype行为变更。

开启safeMode：在Fastjson 1.2.68及之后的版本中，引入了safeMode配置选项。配置safeMode后，无论白名单和黑名单，都不支持autoType，从而可以杜绝反序列化Gadgets类变种攻击。可以通过以下方式开启safeMode：

    在代码中配置：ParserConfig.getGlobalInstance().setSafeMode(true);
    JVM启动参数：-Dfastjson.parser.safeMode=true
    通过fastjson.properties文件配置：fastjson.parser.safeMode=true。

使用AutoTypeCheckHandler：在1.2.68之后的版本，Fastjson提供了AutoTypeCheckHandler扩展，可以自定义类接管autoType。通过ParserConfig#addAutoTypeCheckHandler方法注册，以控制哪些类允许被反序列化。

避免使用@type：在JSON字符串中避免使用@type字段来指定类型，除非完全信任数据来源。

代码审计和安全测试：对使用Fastjson的代码进行审计，确保没有不安全的反序列化操作。同时，进行安全测试，如使用自动化工具检测潜在的反序列化漏洞。

严格控制数据源：确保应用程序不会处理不受信任的JSON数据，严格控制数据输入来源。

使用JSONType注解：在需要反序列化的类上使用@JSONType注解，并结合autoTypeCheckHandler属性，实现更细粒度的控制。

升级到Fastjson v2：Fastjson v2是2.0版本，提供了更多的安全特性和性能提升，不完全兼容1.x版本，但提供了更高的安全性。

    关注官方通告：关注Fastjson官方的安全通告和更新，及时了解和应用安全修复。

使用其他替代组件：使用 gson、Jackson 等替代 fastjson，gson、Jackson 等 json 框架历史的严重安全漏洞相对较少，但是仍然需要及时升级到安全的新版本。

Chanzi-Separator
*/