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
  ('search' IN  sinkNode.selectors AND 'InitialDirContext' IN  sinkNode.receiverTypes) OR
  ('search' IN  sinkNode.selectors AND 'DirContext' IN  sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])

RETURN
  p AS path

/*
Chanzi-Separator

LDAP注入

LDAP注入，也称为轻量级目录访问协议注入，是一种针对Web应用程序的安全漏洞，它允许攻击者通过应用程序的输入接口提交恶意构造的LDAP查询。以下是LDAP注入的原理：

LDAP查询构建：应用程序通常使用用户输入来构建LDAP查询，以便在目录服务中搜索或修改数据。

输入未过滤或未正确转义：如果应用程序未能对用户输入进行适当的过滤、验证或转义，攻击者就可能注入额外的LDAP查询语句。

构造注入语句：攻击者构造特殊的输入，这些输入被应用程序误认为是合法的查询参数，并将其包含在LDAP查询中。

查询修改：通过注入的语句，攻击者可以修改原始的LDAP查询逻辑，导致应用程序执行非预期的查询。

目录服务响应：目录服务接收到修改后的查询，并根据查询的内容返回数据或执行操作。

数据泄露或权限提升：攻击者可以利用LDAP注入来访问敏感数据、修改目录信息或提升权限。

攻击类型：

  信息泄露：通过构造查询来获取目录服务中的敏感信息。

  权限提升：通过注入查询绕过安全限制，访问或修改更高权限的数据。

  拒绝服务：发送恶意查询导致目录服务崩溃或不稳定。

Chanzi-Separator

过滤和验证输入：确保所有用户输入都经过严格的过滤和验证。只允许符合特定模式（如仅字母数字字符）的输入。

使用预编译查询：尽可能使用预编译的LDAP查询或参数化搜索，避免将用户输入直接拼接到查询字符串中。

转义特殊字符：如果用户输入必须包含在LDAP查询中，确保对特殊字符进行适当的转义，以防止它们被解释为LDAP查询的一部分。

限制搜索范围：在LDAP查询中使用限制性更强的搜索过滤器，以减少潜在的注入风险。

使用角色和权限检查：确保应用程序在执行LDAP查询之前进行角色和权限检查，以限制用户的操作范围。

Chanzi-Separator
*/