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
  // jdk 方式
  ('exec' IN  sinkNode.selectors AND 'Runtime' IN  sinkNode.receiverTypes) OR
  sinkNode.AllocationClassName = 'ProcessBuilder' OR
  ('command' IN sinkNode.selectors AND 'ProcessBuilder' IN sinkNode.receiverTypes) OR
  // 自定义方法，比如封装 jsch 调用为工具类，sink 点为方法调用的入参（根据类名、方法名匹配）
  ('execute' IN  sinkNode.selectors AND 'ExecuteShellUtil' IN  sinkNode.receiverTypes) OR
  ('execute' IN  sinkNode.selectors AND 'ExecuteShellUtils' IN  sinkNode.receiverTypes) OR
  ('exec' IN  sinkNode.selectors AND 'ExecuteShellUtil' IN  sinkNode.receiverTypes) OR
  ('exec' IN  sinkNode.selectors AND 'ExecuteShellUtils' IN  sinkNode.receiverTypes) OR
  // 模糊匹配，sink 为方法定义形参（根据方法名、参数名 匹配）
  (sinkNode.method  IN ['execute', 'exec'] AND
  sinkNode.name  IN ['command', 'cmd'])

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  p AS path

/*
Chanzi-Separator

java命令注入

Java命令注入漏洞的原理主要涉及到对用户输入的验证和过滤不足，以及程序在执行系统命令时的不安全操作。

具体来说：

用户输入处理不当：应用程序通常接收用户输入，如表单数据、URL参数等，用于执行各种操作。如果应用程序没有对这些输入进行充分的验证和过滤，恶意用户可能会输入包含恶意命令的数据。

执行系统命令：在Java中，有时需要执行系统命令来完成某些功能，例如通过Runtime.exec()或ProcessBuilder类。如果应用程序直接将未经验证的用户输入用于构建系统命令，那么恶意用户就有可能构造输入，使其包含恶意命令。

命令执行：当应用程序执行这些包含恶意命令的系统命令时，实际上是在操作系统层面上执行了这些命令。这可能导致攻击者获得对系统的未授权访问，执行任意代码，甚至可能完全控制整个系统。

权限提升：如果Java应用程序以高权限用户身份运行（如root或管理员），那么通过命令注入攻击，攻击者可能获得与该用户相同的权限，从而进一步加剧潜在的风险。

Chanzi-Separator

针对Java中的命令注入漏洞，修复建议可以简要总结为以下几点：

输入验证与过滤：对用户输入进行严格的验证和过滤，确保只接受预期格式和长度的数据。对于任何不允许的字符或命令，应进行过滤或转义处理。

使用安全API：避免直接调用执行系统命令的函数，如Runtime.exec()或ProcessBuilder。如果必须执行命令，确保使用安全的API和机制，并对命令和参数进行充分验证。

Chanzi-Separator
*/