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
  ('putTemplate' IN sinkNode.selectors AND 'StringTemplateLoader' IN sinkNode.receivers)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

FreeMarker模版注入

FreeMarker 是一款用 Java 语言编写的模板引擎，主要用于基于模板和数据模型生成文本输出，如 HTML 页面、电子邮件、配置文件等。它被设计为一个通用工具，用于帮助开发者将数据和模板结合起来生成所需的文本输出。FreeMarker 模板使用 FreeMarker Template Language (FTL) 编写，这是一种专门的语言，不同于通用编程语言如 PHP。

FreeMarker 的工作原理可以概括为：模板 + 数据模型 = 输出。在模板中，开发者可以专注于如何展示数据，而在模板之外则可以专注于要展示什么数据。这种方式通常被称为 MVC（模型-视图-控制器）模式，对于动态网页来说，是一种特别流行的模式。它有助于从开发人员（Java 程序员）中分离出网页设计师（HTML 设计师）。

模板注入漏洞（Template Injection）是指攻击者通过向模板引擎输入恶意数据，利用模板引擎解析时的行为来执行攻击者控制的代码。在 FreeMarker 中，这种漏洞通常与以下几个因素有关：

内置函数滥用：FreeMarker 提供了一些内置函数，如 new 和 api，这些函数可以创建 Java 对象或访问 Java API。如果这些函数被滥用，攻击者可能创建恶意对象或执行危险操作。

服务端模板注入（SSTI）：当用户输入被插入到服务器端模板中，并且模板引擎在渲染时执行了这些输入，就可能发生 SSTI 攻击。攻击者可以通过精心构造的输入来控制模板的行为，执行恶意代码。

配置不当：如果 FreeMarker 配置不当，比如允许使用 api_builtin 功能，攻击者可能利用这一点来执行任意代码或读取敏感文件。

模板编辑功能：如果应用允许用户编辑模板，并且没有适当的输入验证和过滤，用户可能注入恶意模板代码，导致 SSTI 攻击。

Chanzi-Separator

FreeMarker模板注入漏洞的修复方案通常涉及以下几个方面：

限制new函数的使用：可以通过设置TemplateClassResolver来限制new函数可以创建的类。从FreeMarker 2.3.17版本开始，官方提供了三种TemplateClassResolver来限制类解析：

UNRESTRICTED_RESOLVER：允许通过new函数获取任何类。

SAFER_RESOLVER：不允许加载freemarker.template.utility.JythonRuntime、freemarker.template.utility.Execute、freemarker.template.utility.ObjectConstructor这三个类。

ALLOWS_NOTHING_RESOLVER：禁止解析任何类。 开发者可以通过调用freemarker.core.Configurable#setNewBuiltinClassResolver方法来设置TemplateClassResolver，从而限制通过new()函数对特定类的解析。

禁用api函数：如果api_builtin_enabled设置为true，则可以使用api函数，但这个配置在2.3.22版本之后默认为false。如果不必要，应该保持它为false以避免潜在的安全风险。

输入验证和过滤：对所有用户输入进行严格的验证和过滤，确保不允许执行恶意代码。

采用前后端分离架构：目前前后端分离架构是更主流的开发方式，数据的渲染交给前端框架，比如 vue、react 等，后端语言不需要进行模板的解析，能够避免 ssti 相关的漏洞。

Chanzi-Separator
*/