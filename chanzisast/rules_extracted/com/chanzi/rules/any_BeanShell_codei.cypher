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
  ('eval' IN sinkNode.selectors AND 'Interpreter' IN sinkNode.receiverTypes) OR
  ('source' IN sinkNode.selectors AND 'Interpreter' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

BeanShell RCE（远程代码执行）

该漏洞允许攻击者远程执行任意代码。这种漏洞通常与Java的BeanShell解释器相关，BeanShell是一个小型的、免费的、可嵌入的Java源解释器，具有使用Java编写的对象脚本语言功能。

攻击者可以通过向BeanShell对应的api接口发送恶意构造的HTTP请求来执行系统命令。例如，通过发送包含exec("whoami");的请求，攻击者可以查看命令执行的结果，从而验证漏洞的存在。

参考：https://github.com/beanshell/beanshell/wiki/Embedding-BeanShell-in-Your-Application

Chanzi-Separator

1. 禁用或移除BeanShell的使用：如果可能，应考虑在应用程序中禁用或移除BeanShell的使用，特别是在处理不受信任的输入时。

2. 输入验证和过滤：对所有外部输入进行严格的验证和过滤，比如有限的白名单校验，确保不允许执行恶意代码。对于BeanShell处理的数据，应确保其来源可靠，并且内容符合预期的格式和结构。

3. 避免用户直接输入表达式：通常不建议直接让用户输入表达式，而是输出特定的参数，经过应用程序的校验后再翻译成对应的BeanShell调用。

Chanzi-Separator
*/