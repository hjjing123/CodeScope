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
  'queryForMap' IN sinkNode.selectors OR
  'queryForObject' IN sinkNode.selectors OR
  'queryForList' IN sinkNode.selectors OR
  'queryForRowSet' IN sinkNode.selectors OR
  'batchUpdate' IN sinkNode.selectors OR
  ('query' IN sinkNode.selectors AND 'JdbcOperations' IN sinkNode.receiverTypes) OR
  ('query' IN sinkNode.selectors AND   'JdbcTemplate' IN  sinkNode.receiverTypes) OR
  ('execute' IN sinkNode.selectors AND   'JdbcTemplate' IN  sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

JdbcTemplate sql注入

在使用JdbcTemplate时，SQL注入的基本原理与在其他数据库访问场景中相同。JdbcTemplate是Spring框架提供的一个用于简化数据库操作的工具类，但它本身并不防止SQL注入。以下是在使用JdbcTemplate时可能发生SQL注入的基本原理：

    动态SQL语句构建：在使用JdbcTemplate执行数据库操作时，经常需要动态构建SQL语句，如根据用户输入构造查询条件。

    用户输入拼接：如果用户输入直接或间接地拼接到SQL语句中，而没有进行适当的处理，就可能被恶意利用。

    缺乏输入验证：应用程序未能对用户输入进行充分的验证或过滤，允许攻击者提交特殊构造的输入。

    SQL语句执行：当包含用户输入的SQL语句被执行时，如果输入中包含恶意SQL代码，这些代码就可能被执行。

    参数化不足：在使用JdbcTemplate时，如果没有使用参数化查询或预编译语句，就可能容易受到SQL注入攻击。

    自动类型转换：JdbcTemplate可能会根据输入的类型自动转换SQL语句，这有时可能导致安全漏洞。

    框架和库的缺陷：虽然JdbcTemplate本身可能不包含缺陷，但应用程序中其他部分的不当使用或配置可能增加SQL注入的风险。

    数据库权限：如果应用程序使用的数据库账户具有较高的权限，SQL注入漏洞的影响可能会更加严重。


Chanzi-Separator

在使用JdbcTemplate时，为了防止SQL注入漏洞，可以采取以下修复建议：

    使用参数化查询：总是使用参数化查询（也称为预编译语句）来避免将用户输入直接拼接到SQL语句中。

    java

    String sql = "SELECT * FROM users WHERE username = ? AND status = ?";
    List<User> users = jdbcTemplate.query(
        sql,
        new Object[] {username, status},
        new RowMapper<User>() {
            // ...
        }
    );

    避免字符串拼接：不要通过字符串拼接的方式构建SQL语句，特别是当涉及到用户输入时。

    使用PreparedStatement：如果需要执行更新操作（如INSERT、UPDATE、DELETE），使用PreparedStatement来防止SQL注入。

    限制用户输入：对用户输入进行严格的验证和过滤，只允许安全字符或符合预期格式的输入。

    使用白名单验证：对于用户输入的验证，使用白名单方法来限制允许的值。

    错误处理：确保数据库操作中的错误处理不会向用户展示敏感的SQL错误信息。

    最小化数据库权限：确保应用程序使用的数据库账户具有执行必要操作的最小权限，避免使用管理员权限。

    使用ORM框架：考虑使用Spring Data JPA或Hibernate等ORM框架，这些框架可以提供额外的安全层，减少直接SQL操作。

通过实施这些措施，可以显著降低使用JdbcTemplate时SQL注入漏洞的风险，并提高应用程序的整体安全性。
Chanzi-Separator
*/