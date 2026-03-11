MATCH
  (sourceNode)
  WHERE
  (

  // jfinal : String keyword=this.getPara("keyword");
    (sourceNode:CallArg AND 'getPara' IN  sourceNode.selectors) OR
    sourceNode.assignRight STARTS WITH 'getParamsMap' OR
    sourceNode.assignRight STARTS WITH 'getParaMap' OR
    // 一些框架自定义注解， 请求入参使用 @HttpParam
    (sourceNode:MethodBinding AND 'HttpParam' IN sourceNode.paramAnnotations)
  ) AND
  NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode)
  WHERE
   ('lookup' IN  sinkNode.selectors AND 'InitialContext' IN  sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

JNDI（Java Naming and Directory Interface）注入漏洞

漏洞主要是由于应用程序在处理用户输入时，未对JNDI服务的lookup()方法调用进行适当的限制或过滤，导致攻击者可以通过构造恶意的JNDI名称来远程加载和执行任意代码。

漏洞原理：
JNDI是Java提供的一种服务，用于访问各种命名和目录服务。在Java应用中，JNDI可以用来通过名称查找对象，这些对象可以是本地的，也可以是远程的。当应用程序使用JNDI查找对象时，如果输入参数没有得到正确的验证和过滤，攻击者可以构造一个恶意的JNDI名称，如ldap://attacker-host/evil，导致应用程序尝试从攻击者控制的服务器加载对象。如果攻击者控制的服务器上放置了恶意的类文件，应用程序加载并执行这些类时，就会执行攻击者的代码
。

利用方式：
攻击者可以利用JNDI注入漏洞通过以下方式：

RMI（Remote Method Invocation）：利用JNDI结合RMI的方式，攻击者可以创建一个恶意的RMI服务器，当受害者的应用程序尝试通过JNDI查找对象时，实际上是连接到了攻击者的RMI服务器，加载并执行攻击者控制的恶意类。
LDAP（Lightweight Directory Access Protocol）：与RMI类似，LDAP也可以用于JNDI注入攻击。攻击者可以设置一个LDAP服务器，受害者的应用程序通过JNDI查找对象时，会从LDAP服务器加载恶意对象。
DNS：攻击者还可以通过DNS服务进行JNDI注入攻击，通过构造特殊的JNDI名称，使应用程序解析恶意的DNS记录。

JNDI注入漏洞是一个严重的安全问题，它可以允许攻击者远程执行任意代码。开发者需要对JNDI服务的使用进行严格的安全审查和限制，以防止潜在的攻击。

Chanzi-Separator

避免直接在代码中进行JNDI的lookup()调用，如果有必要调用建议对 lookup 的参数进行严格的校验，是否为期望的地址。

升级Java版本：确保Java环境是最新的，因为新版本通常会修复已知的安全漏洞。例如，JDK 6u211、7u201、8u191、11.0.1之后的版本中增加了com.sun.jndi.ldap.object.trustURLCodebase的设置，默认为false，禁止LDAP协议使用远程codebase的选项。

升级应用依赖：jndi 技术经常在其他漏洞的利用时使用，如果漏洞是由第三方库引起的，如Apache Log4j2，需要升级到没有漏洞的版本。例如，Log4j2的2.15.0版本对JNDI注入漏洞进行了修复。

网络隔离：确保敏感服务不直接暴露在公共网络下，使用防火墙或其他网络安全设备来限制对JNDI服务的访问，同时限制服务器的出网权限，避免远程下载恶意字节码。

使用安全库：使用安全、更新的库版本，避免使用已知存在安全问题的库。

Chanzi-Separator
*/