MATCH
  (sourceNode)
  WHERE
  (
  sourceNode:DubboServiceArg OR
  sourceNode:JsfXhtmlArg OR
  sourceNode:JaxwsArg OR
  sourceNode:StrutsActionArg OR
  sourceNode:ThriftHandlerArg OR
  sourceNode:NettyHandlerArg OR
    sourceNode:JfinalControllerArg OR
  sourceNode:JbootControllerArg OR
  sourceNode:SpringControllerArg OR
sourceNode:SolonControllerArg OR
  sourceNode:SpringInterceptorArg OR
  sourceNode:JspServiceArg OR
  sourceNode:WebServletArg OR
  sourceNode:WebXmlServletArg OR
  sourceNode:WebXmlFilterArg OR
  sourceNode:JaxrsArg OR
  sourceNode:HttpHandlerArg
  ) AND
  NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode)
  WHERE
  ('connect' IN sinkNode.selectors AND   'Socket' IN  sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

SSRF（Server-Side Request Forgery，服务器端请求伪造）漏洞

ssrf是一种网络安全漏洞，它允许攻击者诱导服务器发起对攻击者选择的服务器的请求。这种漏洞通常发生在服务器接受外部输入作为构造HTTP请求的一部分时。以下是SSRF漏洞的基本原理：

外部输入：应用程序接收来自用户的输入，例如URL、IP地址或其他形式的网络资源引用。

构造请求：应用程序使用这些输入来构造对外部服务器的请求，例如HTTP GET或POST请求。

未充分过滤或验证：如果输入未经充分过滤或验证，攻击者就可能提交特殊构造的输入来利用该漏洞。

请求执行：服务器端应用程序执行构造的请求，而没有意识到它是由攻击者控制的。

访问内部资源：攻击者可能利用SSRF漏洞来访问服务器所在网络中的内部资源，这些资源通常对外部不可见。

    端口扫描：攻击者可以使用SSRF漏洞对内部网络进行端口扫描，寻找开放的端口和运行的服务。

    服务利用：如果攻击者发现某些服务存在漏洞，他们可能尝试进一步利用这些服务来获取敏感信息或执行攻击。

    协议滥用：socket类型的SSRF漏洞可能被用来滥用各种网络协议，如HTTP、FTP、Gopher等。

    防御措施不足：如果应用程序没有实施足够的安全措施来防止SSRF，就可能容易受到攻击。


Chanzi-Separator

以下是Java中SSRF漏洞的修复建议：

限制协议：确保只允许HTTP和HTTPS协议的请求，限制其他可能用于SSRF的协议，如file、ftp等。

白名单过滤：设置白名单，只允许服务器端请求访问特定的、已知安全的域名或IP地址。

输入验证：对所有用户输入进行严格的验证，去除或转义可能用于SSRF的特殊字符，如../、特殊协议头部等。

使用安全的API：避免使用容易受到SSRF攻击的API，比如Java的URL.openStream()等，使用更安全的替代方法。

错误处理：避免在错误消息中显示可能暴露服务器信息的内容，如堆栈跟踪或系统信息。

监控和日志记录：实施监控和日志记录机制，以便检测和响应可能的SSRF尝试。

限制跳转：如果应用程序支持URL重定向，确保限制跳转到特定协议和已知主机，避免使用户能够通过跳转进行SSRF攻击。

使用代理服务器：建立一个代理服务器集群，所有需要访问外部资源的请求都通过这些代理发出，以避免直接从应用服务器发起请求。

限制网络权限：ssrf 漏洞通常配合内网其他漏洞及内网服务器的出网权限进行攻击，限制服务器的出网权限可以有效防止漏洞被成功利用。

积极修复内网漏洞：ssrf 通常用于攻击内网存在漏洞的服务，积极修复内网漏洞可以有效避免 ssrf 的攻击成功率。

Chanzi-Separator
*/