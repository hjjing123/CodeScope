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
  ('evaluate' IN sinkNode.selectors AND 'Velocity' IN sinkNode.receivers) OR
  ('mergeTemplate' IN sinkNode.selectors AND 'Velocity' IN sinkNode.receivers) OR
  ('evaluate' IN sinkNode.selectors AND 'VelocityEngine' IN sinkNode.receivers) OR
  ('mergeTemplate' IN sinkNode.selectors AND 'VelocityEngine' IN sinkNode.receivers) OR
  ('evaluate' IN sinkNode.selectors AND 'RuntimeServices' IN sinkNode.receivers) OR
  ('parse' IN sinkNode.selectors AND 'RuntimeServices' IN sinkNode.receivers) OR
  ('parse' IN sinkNode.selectors AND 'RuntimeSingleton' IN sinkNode.receivers)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

Velocity模板注入漏洞（SSTI）

漏洞的原理是攻击者通过控制Velocity模板的输入，注入恶意的Velocity模板语言（VTL）代码，从而在服务器端执行任意命令。Velocity模板引擎在渲染模板时，会将模板中的变量和表达式替换为实际的值，如果没有对用户的输入进行严格的过滤和验证，攻击者就可以利用这个特点注入恶意代码，导致服务器端的安全问题。

Chanzi-Separator

输入验证：对所有传递给Velocity模板的输入进行严格的验证，确保它们不包含恶意代码。

使用沙箱环境：在沙箱环境中执行Velocity模板，以限制模板可以执行的操作。

升级Velocity版本：使用最新的Velocity版本，因为新版本可能修复了已知的安全漏洞。

监控和日志：加强监控和日志记录，以便在发生安全事件时能够及时发现并响应。

安全审计：定期对应用程序进行安全审计，以发现和修复潜在的安全问题。

用户教育：教育用户不要在应用程序中输入未经验证的代码或表达式。

使用安全的库：如果使用第三方库，确保它们是最新的并且没有已知的安全问题。

自定义SecurityManager：通过自定义SecurityManager来限制Velocity模板可以执行的操作。

使用受限的上下文：在创建VelocityContext时，使用受限的安全上下文，确保只有安全的方法和对象可以被访问。

避免使用Velocity.evaluate：避免直接使用Velocity.evaluate执行未经验证的字符串，因为这可能会导致执行任意代码。

采用前后端分离架构：目前前后端分离架构是更主流的开发方式，数据的渲染交给前端框架，比如 vue、react 等，后端语言不需要进行模板的解析，能够避免 ssti 相关的漏洞。

Chanzi-Separator
*/