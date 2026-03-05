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
  ('createNativeQuery' IN sinkNode.selectors AND 'EntityManager' IN  sinkNode.receiverTypes) OR
  // 匹配这种 String hql ="select id from JC_ORDER where relatebill1 ='" + str +"'";
  (sinkNode.name = 'hql' AND sinkNode.type='String'  AND  (sinkNode:AssignLeft OR sinkNode:LocalDeclaration))
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

JPA SQL注入

在Java中使用JPA（Java Persistence API）时，与使用其他数据库访问技术一样，如果不正确地处理用户输入，可能会产生SQL注入漏洞。以下是在使用JPA时可能产生SQL注入漏洞的基本原理：

动态查询构建：JPA允许动态构建查询，例如使用Criteria API或通过构造字符串查询。如果这些查询包括了未经验证或未经适当处理的用户输入，就可能存在注入风险。

字符串拼接：直接将用户输入拼接到查询字符串中，而不是使用参数化查询，这可能导致SQL注入。

    JPQL/HQL注入：JPQL（Java Persistence Query Language）和HQL（Hibernate Query Language）是JPA中的查询语言，如果允许用户输入直接作为查询的一部分，攻击者可以构造特殊的输入来执行恶意的查询。

    输入未经过滤或验证：应用程序未能对用户输入进行适当的过滤或验证，允许攻击者提交特殊构造的输入。

    使用构造器表达式：在JPA中，可以使用构造器表达式来动态创建查询，如果这些构造器表达式中包含用户输入，就可能产生SQL注入。

    命名查询：如果应用程序使用命名查询，并且这些查询是通过外部配置文件定义的，攻击者可能通过篡改配置文件来注入恶意SQL。

    反射和元编程：JPA支持通过反射和元编程动态地操作实体，如果这些操作中包含了用户控制的数据，也可能产生注入漏洞。

    JPA提供的API滥用：滥用JPA提供的API，如EntityManager.createQuery()，可能不小心将用户输入作为查询的一部分。

    应用程序逻辑缺陷：应用程序逻辑中存在的缺陷，如不正确地处理输入数据，也可能导致SQL注入。


Chanzi-Separator

在使用Java JPA（Java Persistence API）时，为了防止SQL注入漏洞，可以采取以下修复建议：

    使用参数化查询：总是使用命名参数或位置参数来创建查询，避免将用户输入直接拼接到查询字符串中。

    java

String jpql = "SELECT u FROM User u WHERE u.username = :username";
Query query = entityManager.createQuery(jpql);
query.setParameter("username", userInput);

避免构造动态SQL：尽量不要基于用户输入构造动态SQL语句，如果必须这样做，请确保使用安全的API来避免注入。

输入验证：对所有用户输入进行严格的验证，确保它们符合预期的格式，例如使用正则表达式来限制输入。

输入清洗：在将用户输入用于查询之前，进行清洗，去除或转义可能用于SQL注入的字符。

使用JPA Criteria API：Criteria API提供了一种类型安全的方法来构建查询，可以减少直接SQL语句的使用。

java

    CriteriaBuilder cb = entityManager.getCriteriaBuilder();
    CriteriaQuery<User> cq = cb.createQuery(User.class);
    Root<User> root = cq.from(User.class);
    cq.where(cb.equal(root.get("username"), userInput));
    List<User> users = entityManager.createQuery(cq).getResultList();

    限制数据库权限：为应用程序使用的数据库账户设置适当的权限，避免使用具有高权限的账户。

    使用ORM框架的安全特性：如果你使用的是JPA实现，如Hibernate，利用其提供的安全特性，例如自动转义。

    错误处理：确保错误处理不会向用户展示敏感的SQL错误信息。

    使用安全的配置：确保JPA和ORM框架的配置是安全的，例如关闭不必要的JPA功能。

    使用白名单：对于用户输入的验证，使用白名单方法来限制允许的值。

通过实施这些措施，可以显著降低使用JPA时SQL注入漏洞的风险，并提高应用程序的整体安全性。
Chanzi-Separator
*/