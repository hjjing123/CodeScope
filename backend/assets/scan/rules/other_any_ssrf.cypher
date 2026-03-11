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
  // -------------- 基础URL相关（URL作为参数或操作对象）--------------
  ('url' IN sinkNode.selectors AND sinkNode.argPosition = 0) OR  // 方法参数中url为第一个参数
  ('URL' IN sinkNode.selectors AND sinkNode.argPosition = 0) OR  // 大写URL参数
  sinkNode.AllocationClassName = 'URL' OR  // URL对象实例化（构造参数通常为URL字符串）
  (sinkNode.selector = 'getContent' AND sinkNode.type = 'URL') OR  // URL.getContent()无参数
  (sinkNode.selector = 'openConnection' AND sinkNode.type = 'URL') OR  // URL.openConnection()无参数
  (sinkNode.selector = 'openStream' AND sinkNode.type = 'URL') OR  // URL.openStream()无参数
  ('toURI' IN sinkNode.selectors AND sinkNode.type = 'URL' AND sinkNode.argPosition = 0) OR  // URL.toURI()转换可能触发解析

  // -------------- HTTP方法类（URL通常为构造参数或set方法第一个参数）--------------
  sinkNode.AllocationClassName = 'GetMethod' OR  // 构造参数为URL
  sinkNode.AllocationClassName = 'HttpGet' OR  // 构造参数为URL/URI
  sinkNode.AllocationClassName = 'HttpPost' OR  // 构造参数为URL/URI
  sinkNode.AllocationClassName = 'HttpPut' OR  // 构造参数为URL/URI
  sinkNode.AllocationClassName = 'HttpDelete' OR  // 构造参数为URL/URI
  sinkNode.AllocationClassName = 'HttpHead' OR  // 补充HTTP HEAD方法
  sinkNode.AllocationClassName = 'HttpOptions' OR  // 补充HTTP OPTIONS方法
  ('setURI' IN sinkNode.selectors AND 'HttpRequestBase' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // setURI(URI)第一个参数为URI
  ('setUri' IN sinkNode.selectors AND 'AbstractRequestBuilder' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // setUri(String)第一个参数为URL字符串

  // -------------- Apache HttpClient执行方法（URL已封装在请求对象中，无需参数位置）--------------
  ('execute' IN sinkNode.selectors AND 'CloseableHttpClient' IN sinkNode.receiverTypes) OR
  ('execute' IN sinkNode.selectors AND 'CloseableHttpAsyncClient' IN sinkNode.receiverTypes) OR
  ('execute' IN sinkNode.selectors AND 'HttpClient' IN sinkNode.receiverTypes) OR
  ('executeMethod' IN sinkNode.selectors AND 'HttpClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // executeMethod(HttpMethod)第一个参数为请求对象（含URL）
  ('doExecute' IN sinkNode.selectors AND 'AbstractHttpClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 底层执行方法（补充）

  // -------------- Spring框架（URL通常为第一个参数）--------------
  ('exchange' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // exchange(url, ...)第一个参数为URL
  ('getForEntity' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // getForEntity(url, ...)
  ('getForObject' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // getForObject(url, ...)
  ('postForEntity' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // postForEntity(url, ...)
  ('postForLocation' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // postForLocation(url, ...)
  ('postForObject' IN sinkNode.selectors AND 'RestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // postForObject(url, ...)
  ('exchange' IN sinkNode.selectors AND 'AsyncRestTemplate' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // AsyncRestTemplate.exchange(url, ...)
  ('uri' IN sinkNode.selectors AND 'WebClient.RequestHeadersUriSpec' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // WebClient.uri(url)第一个参数为URL
  ('method' IN sinkNode.selectors AND 'WebClient.RequestBodyUriSpec' IN sinkNode.receiverTypes AND sinkNode.argPosition = 1) OR  // WebClient.method(..., url)第二个参数为URL

  // -------------- OkHttp（URL在Request.Builder中为第一个参数）--------------
  ('url' IN sinkNode.selectors AND 'Request.Builder' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Request.Builder.url(url)
  ('newCall' IN sinkNode.selectors AND 'OkHttpClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // newCall(Request)第一个参数含URL
  ('newWebSocket' IN sinkNode.selectors AND 'OkHttpClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // newWebSocket(Request, ...)第一个参数含URL
  ('execute' IN sinkNode.selectors AND 'Call' IN sinkNode.receiverTypes) OR  // Call.execute()执行（含URL的请求）
  ('enqueue' IN sinkNode.selectors AND 'Call' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Call.enqueue(Callback)异步执行（含URL）

  // -------------- Hutool等工具类（URL通常为第一个参数）--------------
  ('createPost' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // HttpUtil.createPost(url)
  ('createGet' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // HttpUtil.createGet(url)
  ('get' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // HttpUtil.get(url)
  ('post' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // HttpUtil.post(url)
  ('downloadFileFromUrl' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 第一个参数为URL
  ('of' IN sinkNode.selectors AND 'HttpRequest' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // HttpRequest.of(url)
  ('download' IN sinkNode.selectors AND 'HttpUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 补充下载方法
  ('readBytes' IN sinkNode.selectors AND 'ResourceUtil' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Hutool ResourceUtil读取URL资源

  // -------------- XML解析（外部实体URL通常为第一个参数）--------------
  sinkNode.AllocationClassName = 'XmlStreamReader' OR  // XML流读取器（可能处理外部实体）
  ('parse' IN sinkNode.selectors AND 'XMLReader' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // XMLReader.parse(url)
  ('parse' IN sinkNode.selectors AND 'DocumentBuilder' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // DocumentBuilder.parse(url)
  ('setFeature' IN sinkNode.selectors AND 'DocumentBuilderFactory' IN sinkNode.receiverTypes AND sinkNode.argPosition = 1) OR  // 关闭外部实体限制的方法（间接风险）

  // -------------- 数据库连接（URL为第一个参数）--------------
  ('getConnection' IN sinkNode.selectors AND 'DriverManager' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // getConnection(url, ...)
  ('getConnection' IN sinkNode.selectors AND 'DataSource' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // DataSource.getConnection(url, ...)
  ('setJdbcUrl' IN sinkNode.selectors AND 'HikariConfig' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // setJdbcUrl(url)
  ('setUrl' IN sinkNode.selectors AND 'DruidDataSource' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // setUrl(url)
  ('setUrl' IN sinkNode.selectors AND 'BasicDataSource' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 补充DBCP连接池

  // -------------- 文件处理（URL为第一个参数）--------------
  ('connect' IN sinkNode.selectors AND 'Jsoup' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)
  ('copyURLToFile' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // copyURLToFile(url, ...)
  ('copy' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Files.copy(url, ...)
  ('toFile' IN sinkNode.selectors AND 'URL' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // URL.toFile(path)（path可能含URL）
  ('read' IN sinkNode.selectors AND 'ImageIO' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // ImageIO.read(URL)读取网络图片
  ('copyFile' IN sinkNode.selectors AND 'PathUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 补充PathUtils文件复制（含URL路径）

  // -------------- com.gitee.httphelper（URL为第一个参数）--------------
  ('get' IN sinkNode.selectors AND 'HttpHelper' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)
  ('post' IN sinkNode.selectors AND 'HttpHelper' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)
  ('postJson' IN sinkNode.selectors AND 'HttpHelper' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)
  ('postText' IN sinkNode.selectors AND 'HttpHelper' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)
  ('postForm' IN sinkNode.selectors AND 'HttpHelper' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Jsoup.connect(url)

  // -------------- 其他框架/协议（URL为第一个参数）--------------
  ('create' IN sinkNode.selectors AND 'Retrofit.Builder' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Retrofit.Builder.baseUrl(url)
  ('target' IN sinkNode.selectors AND 'Client' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // JAX-RS Client.target(url)
  ('connect' IN sinkNode.selectors AND 'FTPClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // FTPClient.connect(host)
  ('connect' IN sinkNode.selectors AND 'SMTPClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 补充SMTP协议
  ('connect' IN sinkNode.selectors AND 'POP3Client' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 补充POP3协议
  ('url' IN sinkNode.selectors AND 'WSClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // WebSocket客户端设置URL
  ('subscribe' IN sinkNode.selectors AND 'StompClient' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0)  // STOMP协议订阅（含URL）

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Boolean','Integer', 'int', 'long'])
RETURN
  p AS path

/*
Chanzi-Separator

SSRF（Server-Side Request Forgery，服务器端请求伪造）

ssrf漏洞是一种网络安全漏洞，它允许攻击者诱导服务器发起对攻击者选择的服务器的请求。这种漏洞通常发生在服务器接受外部输入作为构造HTTP请求的一部分时。以下是SSRF漏洞的基本原理：

1.外部输入：应用程序接收来自用户的输入，例如URL、IP地址或其他形式的网络资源引用。

2.构造请求：应用程序使用这些输入来构造对外部服务器的请求，例如HTTP GET或POST请求。

3.未充分过滤或验证：如果输入未经充分过滤或验证，攻击者就可能提交特殊构造的输入来利用该漏洞。

4.请求执行：服务器端应用程序执行构造的请求，而没有意识到它是由攻击者控制的。

5.访问内部资源：攻击者可能利用SSRF漏洞来访问服务器所在网络中的内部资源，这些资源通常对外部不可见。

6.端口扫描：攻击者可以使用SSRF漏洞对内部网络进行端口扫描，寻找开放的端口和运行的服务。

7.漏洞利用：如果攻击者发现某些服务存在漏洞，他们可能尝试进一步利用这些服务来获取敏感信息或执行攻击。

Chanzi-Separator

以下是Java中SSRF漏洞的修复建议：

限制协议：确保只允许HTTP和HTTPS协议的请求，限制其他可能用于SSRF的协议，如file、ftp等。

白名单过滤：设置白名单，只允许服务器端请求访问特定的、已知安全的域名或IP地址。

输入验证：对所有用户输入进行严格的验证，去除或转义可能用于SSRF的特殊字符，如../、特殊协议头部等。

使用安全的API：避免使用容易受到SSRF攻击的API，比如Java的URL.openStream()等，使用更安全的替代方法。

错误处理：避免在错误消息中显示可能暴露服务器信息的内容，如堆栈跟踪或系统信息。

监控和日志记录：实施监控和日志记录机制，以便检测和响应可能的SSRF尝试。

限制跳转：如果应用程序支持URL重定向，确保限制跳转到特定协议和已知主机，避免使用户能够通过跳转进行SSRF攻击。

使用代理服务器：建立一个代理服务器集群，所有需要访问外部资源的请求都通过这些代理发出，以避免直接从应用服务器发起请求。

限制网络权限：ssrf 漏洞通常配合内网其他漏洞及内网服务器的出网权限进行攻击，限制服务器的出网权限可以有效防止漏洞被成功利用。

积极修复内网漏洞：ssrf 通常用于攻击内网存在漏洞的服务，积极修复内网漏洞可以有效避免 ssrf 的攻击成功率。

Chanzi-Separator
*/