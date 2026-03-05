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
  ('prepareCall' IN  sinkNode.selectors AND 'Connection' IN  sinkNode.receiverTypes) OR
  ('execute' IN  sinkNode.selectors AND 'Statement' IN  sinkNode.receiverTypes) OR
  ('executeUpdate' IN  sinkNode.selectors AND 'Statement' IN  sinkNode.receiverTypes) OR
  ('executeQuery' IN  sinkNode.selectors AND 'Statement' IN  sinkNode.receiverTypes) OR
  ('prepareStatement' IN  sinkNode.selectors AND 'Connection' IN  sinkNode.receiverTypes) OR
  // 匹配这种 String sql ="select id from JC_ORDER where relatebill1 ='" + str +"'";
  //(sinkNode.name = 'sql' AND sinkNode.type='String'  AND  (sinkNode:AssignLeft OR sinkNode:LocalDeclaration))
  (sinkNode.name IN ['sql', 'hql', 'querySql', 'updateSql', 'nativeSql'] AND sinkNode.type='String' AND (sinkNode:AssignLeft OR sinkNode:LocalDeclaration))

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

jdbc sql注入

Java中SQL注入漏洞的基本原理与在其他编程环境中的SQL注入类似，都是由于应用程序未能充分验证用户输入，导致攻击者能够在数据库查询中插入恶意SQL代码。以下是SQL注入漏洞的基本原理：

用户输入：攻击者通过应用程序的输入接口提交数据，这些数据可能包括表单字段、URL参数、HTTP头部等。

输入未经过滤或验证：如果应用程序未能对用户输入进行适当的过滤或验证，攻击者就可能提交特殊构造的输入。

构造SQL语句：应用程序通常将用户输入拼接到SQL查询中，以动态生成SQL语句。

SQL语句执行：如果输入被包含在SQL语句中，且未经适当转义，攻击者构造的SQL代码就可能被数据库执行。

攻击目的：攻击者可以利用SQL注入漏洞来访问、修改或删除数据库中的敏感数据，甚至可能通过数据库提权攻击来获取系统级别的访问权限。

数据库权限：如果应用程序使用的数据库账户具有较高的权限，SQL注入漏洞的影响可能会更加严重。

防御不足：如果应用程序缺乏足够的安全措施来防止SQL注入，就可能容易受到攻击。


Chanzi-Separator

修复Java中SQL注入漏洞需要采取一系列的预防措施和安全实践。以下是一些关键的修复建议：

使用预编译语句（PreparedStatement）：使用预编译的SQL语句可以避免SQL注入，因为它们使用参数化查询，而不是将用户输入直接拼接到SQL语句中。

    java

    String sql = "SELECT * FROM users WHERE username = ? AND password = ?";
    PreparedStatement stmt = connection.prepareStatement(sql);
    stmt.setString(1, username);
    stmt.setString(2, password);

参数化查询：确保所有的数据库查询都是参数化的，这可以防止用户输入被解释为SQL代码的一部分，对于无法使用参数化的场景使用输入验证。

输入验证：对所有用户输入进行严格的验证，确保它们符合预期的格式，例如使用正则表达式来验证输入。

最小权限原则：确保数据库账户仅具有完成其任务所必需的最小权限，避免使用具有高权限的账户。

使用ORM框架：使用对象关系映射（ORM）框架，如Hibernate，这些框架通常提供了内置的防护措施来防止SQL注入。

错误处理：不要在生产环境中向用户显示数据库错误信息，这可能会泄露敏感的数据库结构信息或数据库数据。

使用白名单验证：对于输入应限制为预定义的选项或值，使用白名单验证方法来限制用户输入。

使用Web应用防火墙（WAF）：部署WAF可以帮助识别和阻止SQL注入攻击，提升攻击门槛，但是 waf 有其局限性，无法完全防止攻击。

限制数据访问：在可能的情况下，限制应用程序对数据库的访问，例如通过使用视图或存储过程。

通过实施这些措施，可以显著降低Java应用程序中SQL注入漏洞的风险，并提高应用程序的整体安全性。
Chanzi-Separator
*/