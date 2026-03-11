MATCH
  (sourceNode:DubboServiceArg|JaxwsArg|StrutsActionArg|ThriftHandlerArg|NettyHandlerArg|JfinalControllerArg|SpringControllerArg|JspServiceArg|WebServletArg|WebXmlServletArg|WebXmlFilterArg|JaxrsArg|HttpHandlerArg)
WHERE
// 这条规则目前只考虑 订单id 账单id 的 越权查询 ， 其他id的越权，用户可复制此规则，修改id参数
  LOWER(sourceNode.name) = 'orderid' OR
  LOWER(sourceNode.name) = 'order_id' OR
  LOWER(sourceNode.name) = 'billid' OR
  LOWER(sourceNode.name) = 'bill_id' OR
// flatArgs 是入参类型dto 展开后的参数名列表，字符串数组
any(
  x IN sourceNode.flatArgs WHERE
    LOWER(x) = 'orderid' OR
    LOWER(x) = 'billid' OR
    LOWER(x) = 'order_id' OR
    LOWER(x) = 'bill_id'
)

MATCH
  (sinkNode)
  WHERE
  // 数据库查询 jdbctemplate
  ('executeQuery' IN sinkNode.selectors AND 'Statement' IN sinkNode.receiverTypes) OR
  ('executeQuery' IN sinkNode.selectors AND   'PreparedStatement' IN  sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.selectors IS NOT NULL AND 'checkPermission' IN n.selectors)

RETURN
  p AS path

/*
Chanzi-Separator

水平越权漏洞

水平越权漏洞（Horizontal Privilege Escalation，其缩写是HPE）是Web应用程序中一种常见的安全漏洞，它发生在具有相同权限级别的用户之间。攻击者通过利用这些漏洞，可以访问其他用户拥有的资源或执行与其权限级别不符的操作。

原理

水平越权漏洞的原理在于系统未能正确验证用户身份，导致具有相同权限级别的用户可以访问彼此的数据。例如，在一个电商系统中，如果用户A和用户B具有相同的权限级别，系统在处理用户A对订单信息的访问时，如果没有对用户身份进行精确验证，攻击者可能通过修改请求中的某些参数，使系统误认为是用户B在访问订单信息，从而获取用户B的订单详情。

常见参数

水平越权漏洞常见于涉及用户数据操作的参数，如用户ID、订单ID、手机号、卡号、员工编号等。攻击者通过修改这些参数，尝试访问或操作其他用户的数据。

Chanzi-Separator

修复方案

1. 带userid查询：在对数据库操作时，将用户id、资源 id 同时作为查询条件，可以防止操作其他用户的资源。

2. 权限验证：在调用功能前验证用户是否有权限调用相关资源，在执行关键操作前验证用户身份，确保用户具备操作数据资源的权限。

3. 加密资源ID：对直接对象引用的加密资源ID，防止攻击者枚举或伪造ID参数。

4. 不信任用户输入：永远不要相信来自用户的输入，对于可控参数进行严格的检查与过滤。

Chanzi-Separator
*/