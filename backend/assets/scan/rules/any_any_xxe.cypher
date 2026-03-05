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
    NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse'] AND
    (
      (sourceNode.paramAnnotations IS NOT NULL AND any(x IN sourceNode.paramAnnotations WHERE x CONTAINS 'RequestBody')) OR
      toLower(coalesce(sourceNode.name, '')) =~ '.*(xml|content|payload|body|input|data|text).*'
    )

MATCH
  (sinkNode)
  WHERE
  sinkNode.AllocationClassName = 'XSSFWorkbook' OR
  'setByteStream' IN sinkNode.selectors OR
  'createXMLStreamReader' IN sinkNode.selectors OR
  ( 'StreamingReader.builder()' IN sinkNode.receivers AND  'open' IN sinkNode.selectors) OR
  ( 'read' IN sinkNode.selectors AND  'SAXReader' IN sinkNode.receiverTypes) OR
  ( 'parse' IN sinkNode.selectors AND  'XMLReader' IN sinkNode.receiverTypes) OR
  ( 'build' IN sinkNode.selectors AND  'SAXBuilder' IN sinkNode.receiverTypes) OR
  ( 'parse' IN sinkNode.selectors AND  'SAXParser' IN sinkNode.receiverTypes) OR
  ( 'parse' IN sinkNode.selectors AND  'DocumentBuilder' IN sinkNode.receiverTypes) OR
  ( 'parse' IN sinkNode.selectors AND  'Digester' IN sinkNode.receiverTypes) OR
  ( 'parseText' IN sinkNode.selectors AND  'DocumentHelper' IN sinkNode.receiverTypes) OR
  ( 'transform' IN sinkNode.selectors AND  'Transformer' IN sinkNode.receiverTypes) OR
  ( 'read' IN sinkNode.selectors AND  'NodeBuilder' IN sinkNode.receiverTypes) OR
//  ( 'format' IN sinkNode.selectors AND  'Formatter' IN sinkNode.receiverTypes) OR
  ( 'newSchema' IN sinkNode.selectors AND  'SchemaFactory' IN sinkNode.receiverTypes) OR
  ( 'evaluate' IN sinkNode.selectors AND  'XPathExpression' IN sinkNode.receiverTypes) OR
  ( 'validate' IN sinkNode.selectors AND  'Persister' IN sinkNode.receiverTypes) OR
  ( 'read' IN sinkNode.selectors AND  'Persister' IN sinkNode.receiverTypes) OR
  ( 'provide' IN sinkNode.selectors AND  'DocumentProvider' IN sinkNode.receiverTypes) OR
  ( 'provide' IN sinkNode.selectors AND  'StreamProvider' IN sinkNode.receiverTypes) OR
  ( 'newTransformer' IN sinkNode.selectors AND  'TransformerFactory' IN sinkNode.receiverTypes) OR
  ( 'newTransformer' IN sinkNode.selectors AND  'SAXTransformerFactory' IN sinkNode.receiverTypes) OR
  ( 'newXMLFilter' IN sinkNode.selectors AND  'SAXTransformerFactory' IN sinkNode.receiverTypes) OR
  // hutool  只在 disallow-doctype-decl 为 false 时 有漏洞
  ( 'parseXml' IN sinkNode.selectors AND  'XmlUtil' IN sinkNode.receiverTypes) OR
  ( 'unmarshal' IN sinkNode.selectors AND  'Unmarshaller' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..30]->(sinkNode))
WHERE
  NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )
WITH sourceNode, sinkNode, p
ORDER BY length(p) ASC
WITH
  coalesce(sourceNode.name, '') AS sName,
  coalesce(sourceNode.method, '') AS sMethod,
  coalesce(sourceNode.type, '') AS sType,
  coalesce(sinkNode.selector, '') AS sinkSelector,
  coalesce(sinkNode.methodFullName, '') AS sinkMfn,
  coalesce(sinkNode.AllocationClassName, '') AS sinkAlloc,
  collect(p)[0] AS path
RETURN
  path AS path

/*
Chanzi-Separator

XXE（XML外部实体攻击，XML External Entity Attack）

xxe漏洞是一种影响XML处理器的安全漏洞。当XML文档允许引用外部实体时，如果没有得到正确处理，攻击者可以利用这个漏洞来读取服务器上的文件、执行拒绝服务攻击（DoS），甚至在某些情况下执行远程服务器的攻击。以下是XXE漏洞的基本原理：

XML和DTD：XML文档可以使用DTD（文档类型定义）来定义合法的文档结构。DTD可以是内部定义的，也可以引用外部定义。

外部实体引用：在DTD中，可以定义外部实体，这些实体可以引用外部资源，如文件系统中的文件或网络上的资源。

漏洞触发：如果XML解析器配置不当，允许引用外部实体，攻击者可以构造特殊的XML输入，其中包含对外部实体的引用。

文件读取：攻击者可以利用XXE漏洞尝试读取服务器上的敏感文件，例如配置文件、源代码等。

拒绝服务攻击：攻击者可以构造一个指向大型文件或无限循环的外部实体引用，导致XML解析器消耗大量资源，从而实现拒绝服务攻击。

远程服务器攻击：如果允许通过网络引用外部资源，攻击者可以利用这一点来发起远程服务器攻击，例如尝试读取远程服务器上的文件。

配置不当的XML解析器：很多XML解析器默认允许处理外部实体，如果应用程序没有正确配置解析器，就可能受到XXE攻击。

防御不足：如果应用程序没有实施足够的安全措施来防止XXE攻击，就可能容易受到攻击。


Chanzi-Separator

修复Java中XXE（XML外部实体攻击）漏洞需要开发者采取以下步骤和策略：

禁用外部实体处理：确保XML解析器配置为禁用对外部实体的解析。这可以通过设置XML处理器的属性来完成。

使用安全的解析器：选择不容易受到XXE攻击的XML解析器，例如使用不支持外部实体解析的解析器。

输入验证：对所有传入的XML数据进行严格的验证，确保它们不包含对外部实体的引用。

使用白名单：如果应用程序需要引用外部资源，使用白名单来限制可引用的资源，只允许特定的、已知安全的资源被引用。

限制DTD使用：避免在XML文档中使用DTD（文档类型定义），或者确保DTD是安全的，不包含对外部实体的引用。

错误消息处理：确保错误消息不会泄露有关XML解析器配置或文件路径的信息。

使用安全的库：使用成熟的库来处理XML数据，避免使用可能容易受到XXE攻击的旧库。

使用安全的XML处理API：在Java中，使用如javax.xml.parsers.DocumentBuilder时，确保禁用外部实体的解析，例如通过设置DocumentBuilderFactory的setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)。

配置安全的XML解析器：如果使用SAX解析器，确保配置它以避免解析外部实体，例如使用setEntityResolver方法来返回一个自定义的EntityResolver。

使用 json 代替 xml：针对用户的输入，通常建议优先考虑使用 json 格式代替 xml 格式，有更高的安全性，xml 由于其复杂的 dtd、scheme 等机制更易受到攻击。

Chanzi-Separator
*/
