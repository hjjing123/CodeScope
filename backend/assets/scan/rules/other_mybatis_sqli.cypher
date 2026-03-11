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
  WHERE sinkNode:MybatisXmlUnsafeArg OR sinkNode:MybatisAnnotationUnsafeArg
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

mybatis sql注入

在使用MyBatis时，SQL注入漏洞的产生原理与直接使用JDBC或JPA时类似，主要是因为应用程序未能正确处理用户输入，导致攻击者能够在SQL语句中注入恶意代码。以下是MyBatis中产生SQL注入漏洞的原理：

    动态SQL：MyBatis支持动态SQL，允许根据条件动态地拼接SQL语句。如果这些条件中包含了未经过滤或未经验证的用户输入，就可能被攻击者利用。

    用户输入拼接：如果用户输入被直接拼接到SQL语句中，而不是作为参数传递，攻击者可以通过构造特殊输入来注入恶意SQL代码。

    MyBatis的脚本功能：MyBatis允许在XML映射文件或注解中使用脚本语言（如JavaScript），如果用户能够控制脚本中的输入，就可能产生注入风险。

    XML映射文件的配置：如果MyBatis的XML映射文件或注解被配置为直接包含用户输入，而不是使用预编译的SQL语句或参数化查询，就可能产生SQL注入漏洞。

    缺乏输入验证：应用程序未能对用户输入进行适当的验证和过滤，允许攻击者提交特殊构造的输入。

    MyBatis的动态语言支持：MyBatis的动态SQL功能，如 script 标签，允许执行复杂的动态SQL语句。如果这些语句中包含了用户输入，就可能被利用来执行SQL注入。

    数据库权限：如果应用程序使用的数据库账户具有较高的权限，SQL注入漏洞的影响可能会更加严重。

    MyBatis配置不当：MyBatis配置不当，如允许动态生成SQL语句而没有适当的安全措施，也可能增加SQL注入的风险。


Chanzi-Separator

在使用MyBatis时，为了防止SQL注入漏洞，可以采取以下修复建议：

    使用预编译语句：MyBatis支持预编译语句，确保使用参数化查询而不是字符串拼接来构建SQL语句。

    避免动态SQL拼接：不要在MyBatis的XML映射文件或注解中直接使用用户输入拼接SQL语句。

    输入验证：对所有用户输入进行严格的验证，确保它们符合预期格式，避免恶意输入。

    使用MyBatis的动态SQL特性：MyBatis提供了#{}和${}作为参数占位符。始终使用#{}来防止SQL注入，因为它会将输入转义；而${}则需要谨慎使用，因为它会直接将内容插入SQL语句。

    最小化权限：确保应用程序使用的数据库账户具有执行必要操作的最小权限。

    使用Type Handlers：MyBatis允许自定义Type Handlers来处理输入和输出的转换，确保这些处理器是安全的。

    错误处理：确保错误处理不会向用户展示敏感的SQL错误信息。

    更新和补丁：保持MyBatis和数据库驱动程序的更新，应用安全补丁来修复已知的安全漏洞。

    使用MyBatis的插件机制：MyBatis允许使用插件来拦截和处理SQL语句，可以开发自定义插件来检测和防止SQL注入。

    使用白名单：对于输入应限制为预定义的选项或值，使用白名单验证方法来限制用户输入。

Chanzi-Separator
*/