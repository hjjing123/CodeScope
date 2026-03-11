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
  // -------------- 基础文件输入流（直接读取文件）--------------
  sinkNode.AllocationClassName = 'FileInputStream' OR  // 构造函数接收文件路径
  sinkNode.AllocationClassName = 'FileReader' OR  // 字符流读取文件
  sinkNode.AllocationClassName = 'RandomAccessFile' OR  // 随机访问文件（可读写）
  sinkNode.AllocationClassName = 'Scanner' AND ('File' IN sinkNode.receiverTypes OR 'String' IN sinkNode.receiverTypes) OR  // Scanner读取文件（路径参数）
  ('openStream' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // File.openStream()获取输入流
  ('newInputStream' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // File.newInputStream()（NIO）

  // -------------- Java NIO文件读取（现代API）--------------
  ('toByteArray' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Files.toByteArray(Path) 路径为第一个参数
  ('readAllLines' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 读取所有行（路径参数）
  ('readAllBytes' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 读取所有字节
  ('readString' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 读取字符串（Java 11+）
  ('newInputStream' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 打开文件输入流
  ('walk' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Files.walk(Path) 遍历目录
  ('list' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 列出目录内容（遍历风险）

  // -------------- Apache Commons IO工具类--------------
  ('readToString' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 读取文件为字符串（文件路径参数）
  ('readLines' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 按行读取
  ('readFileToByteArray' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 文件转字节数组
  ('contentEquals' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 比较文件内容（需读取文件）
  ('listFiles' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 列出目录文件（遍历风险）

  // -------------- IOUtils等流操作工具类--------------
  ('toString' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // IOUtils.toString(InputStream) 流可能来自文件
  ('toByteArray' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 输入流转字节数组
  ('readLines' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 读取流的行
  ('copy' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 复制流（源为文件输入流）

  // -------------- Web框架文件下载（直接向响应输出文件）--------------
  ('write' IN sinkNode.selectors AND 'HttpServletResponse' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 向响应写入文件内容
  ('getOutputStream' IN sinkNode.selectors AND 'HttpServletResponse' IN sinkNode.receiverTypes) OR  // 获取响应输出流（用于写入文件）
//  ('sendRedirect' IN sinkNode.selectors AND 'HttpServletResponse' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 重定向到文件路径（可能遍历）
  ('download' IN sinkNode.selectors AND 'WebUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Spring WebUtils下载文件

  // -------------- 框架特定文件读取--------------
  ('getResourceAsStream' IN sinkNode.selectors AND 'ResourceLoader' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Spring资源加载（可能读取任意文件）
  ('getFile' IN sinkNode.selectors AND 'Resource' IN sinkNode.receiverTypes) OR  // Spring Resource获取文件
  ('read' IN sinkNode.selectors AND 'FileSystemResource' IN sinkNode.receiverTypes) OR  // 文件系统资源读取

  // -------------- 其他文件读取/遍历场景--------------
  ('exists' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 判断文件是否存在（路径探测）
  ('isFile' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 判断是否为文件（辅助遍历）
  ('isDirectory' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 判断是否为目录（辅助遍历）
  ('listFiles' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // File.listFiles() 目录遍历
  ('length' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 获取文件大小（需访问文件）
  ('getCanonicalPath' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes)  // 获取规范路径（可能泄露路径信息）

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  p AS path


/*
Chanzi-Separator

目录穿越

Java中的目录穿越漏洞，通常也称为路径穿越漏洞（Path Traversal），是一种安全漏洞，它允许攻击者通过应用程序的输入接口访问或操作应用程序文件系统上的非预期文件和目录。以下是目录穿越漏洞的原理：

输入接口：漏洞通常发生在应用程序接受用户输入作为文件路径或名称的地方。

输入未过滤或未正确处理：如果应用程序未能对用户输入进行适当的过滤或处理，攻击者就可能提交特殊构造的输入来利用该漏洞。

路径解析漏洞：攻击者利用文件系统路径解析的漏洞，通过输入如../（父目录）的序列来上升目录层次结构。

访问控制绕过：通过目录穿越，攻击者可能绕过应用程序的访问控制机制，访问受限目录或文件。

文件泄露：攻击者可能利用此漏洞来下载或查看应用程序的配置文件、源代码、敏感数据等。

文件操作：在某些情况下，攻击者可能不仅能够访问文件，还能够修改或删除它们。

Web应用程序中的体现：在Web应用程序中，目录穿越漏洞可能通过URL参数、表单字段或其他HTTP请求部分传递的输入参数来触发。

Chanzi-Separator

输入验证：对所有用户输入进行严格的验证，确保它们不包含潜在的危险字符或模式，如..、/、\等。

路径规范化：在处理任何用户输入的文件路径之前，使用Java的java.nio.file.Paths.get()方法或相似的库函数对其进行规范化，以消除任何相对路径组件。

使用白名单：对于允许用户上传或下载的文件类型和扩展名，使用白名单验证方法来限制用户输入。

绝对路径：总是使用绝对路径来访问文件系统资源，避免使用相对路径。

限制文件访问范围：确保应用程序的文件操作被限制在特定的目录内，不允许访问该目录之外的文件。

避免使用用户输入作为路径：如果可能，不要直接使用用户输入作为文件路径，可以考虑使用文件id等代替直接输入路径。

文件权限：为应用程序运行的账户设置适当的文件权限，确保它们只能访问必要的文件和目录。

错误处理：在错误处理中避免泄露文件系统结构信息，确保错误消息不会暴露应用程序的内部文件路径。

使用安全的API：使用Java提供的安全的文件操作API，避免使用可能容易受到目录穿越攻击的旧API。

使用文件名哈希：对于上传的文件，使用哈希函数生成新的文件名，避免使用用户指定的文件名。

避免路径拼接：避免使用字符串拼接来构建文件路径，这可能容易出错并导致安全漏洞。

检查文件存在性：在允许文件访问之前，检查文件是否存在，避免攻击者通过指定不存在的文件来绕过检查。

使用安全的配置：确保应用程序的配置文件不包含硬编码的文件路径，或者如果必须包含，确保它们是安全的。

Chanzi-Separator
*/