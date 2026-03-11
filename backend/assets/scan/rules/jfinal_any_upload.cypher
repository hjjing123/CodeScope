// jfinal Controller 子类获取request的方式  ： HttpServletRequest request = this.getRequest();
MATCH
  (sourceNode:ThisReference)
  WHERE sourceNode.selector = 'getRequest' AND sourceNode:Receiver

MATCH
  (sinkNode)
  WHERE
  // -------------- 基础文件输出流（直接写入文件系统）--------------
  sinkNode.AllocationClassName = 'FileOutputStream' OR  // 构造函数接收文件路径，直接写入
  sinkNode.AllocationClassName = 'FileWriter' OR  // 字符流写入文件
  sinkNode.AllocationClassName = 'BufferedOutputStream' OR  // 缓冲输出流（常包装文件流）
  ('write' IN sinkNode.selectors AND 'FileOutputStream' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 写入字节（第一个参数为数据）
  ('write' IN sinkNode.selectors AND 'FileWriter' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 写入字符（第一个参数为数据）
  ('write' IN sinkNode.selectors AND 'BufferedOutputStream' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 缓冲流写入

  // -------------- Spring MultipartFile相关（Web文件上传核心）--------------
  (sinkNode.selector = 'getInputStream' AND sinkNode.type = 'MultipartFile') OR  // 获取上传文件输入流（风险：未校验直接处理）
  (sinkNode.selector = 'getBytes' AND sinkNode.type = 'MultipartFile') OR  // 获取文件字节数组（可能用于写入）
  (sinkNode.selector = 'transferTo' AND sinkNode.type = 'MultipartFile' AND sinkNode.argPosition = 0) OR  // 直接转存到文件（参数为目标路径/File）
  (sinkNode.selector = 'getOriginalFilename' AND sinkNode.type = 'MultipartFile') OR  // 获取原始文件名（风险：未过滤直接用作保存名）

  // -------------- Servlet文件上传（传统Web框架）--------------
  ('parseRequest' IN sinkNode.selectors AND 'ServletFileUpload' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 解析上传请求（获取文件项）
  ('write' IN sinkNode.selectors AND 'FileItem' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // FileItem.write(File) 直接写入
  ('getInputStream' IN sinkNode.selectors AND 'FileItem' IN sinkNode.receiverTypes) OR  // 获取文件项输入流（未校验风险）

  // -------------- Java NIO文件操作（现代文件API）--------------
  ('write' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Files.write(Path, 数据) 第一个参数为路径
  ('copy' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 1) OR  // Files.copy(输入流, 目标路径) 第二个参数为路径
  ('newByteChannel' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 打开文件通道（用于写入）

  // -------------- 工具类文件操作（Apache/Guava等）--------------
  ('copyInputStreamToFile' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 1) OR  // 输入流复制到文件（第二个参数为目标文件）
  ('writeByteArrayToFile' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 字节数组写入文件（第一个参数为文件）
  ('copy' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes AND sinkNode.argPosition = 1) OR  // IOUtils.copy(输入流, 输出流) 输出流可能指向文件
  ('toFile' IN sinkNode.selectors AND 'ByteSource' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // Guava ByteSource写入文件

  // -------------- 框架/服务层文件处理--------------
  ('uploadFile' IN sinkNode.selectors AND 'FileUploadService' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 自定义上传服务（第一个参数为文件/路径）
  ('save' IN sinkNode.selectors AND 'StorageService' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 存储服务保存文件
  ('handleFileUpload' IN sinkNode.selectors AND 'UploadController' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0) OR  // 控制器处理上传

  // -------------- 特殊文件操作（风险较高）--------------
  ('createNewFile' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 创建新文件（路径可控风险）
  ('mkdirs' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR  // 创建目录（路径可控可能导致路径穿越）
  ('renameTo' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes AND sinkNode.argPosition = 0)  // 文件重命名（目标路径可控风险）

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  p AS path


/*
Chanzi-Separator

文件上传漏洞

文件上传基本原理涉及到Web应用程序如何处理用户上传的文件。以下是这一漏洞的关键点：

    用户上传接口：Web应用程序通常包含上传文件的功能，允许用户将文件（如图片、文档等）上传到服务器。

    输入验证不足：如果应用程序未能充分验证用户上传的文件类型和内容，就可能允许恶意文件上传。

    文件类型过滤：应用程序可能通过检查文件扩展名或MIME类型来限制允许上传的文件类型。然而，这种方法不安全，因为扩展名和MIME类型可以被伪造。

    执行权限：如果上传的文件（特别是脚本或可执行文件）被放置在具有执行权限的目录中，它们可能被Web服务器执行。

    路径遍历：攻击者可能尝试通过在文件名中使用特殊字符（如../）来访问服务器上的其他目录和文件。

    服务端解析漏洞：某些Web服务器或应用程序可能存在解析漏洞，允许对特定类型的文件进行错误的解释，例如将一个看起来像图片的文件解析为可执行脚本。

    文件包含漏洞：如果应用程序使用用户可控的输入来包含文件，攻击者可能利用这一点来包含并执行上传的恶意文件。

    存储位置：如果上传的文件存储在Web根目录或可公开访问的位置，攻击者可能直接通过URL访问这些文件。

    访问控制：应用程序可能未能正确实施访问控制，允许未经授权的用户访问或执行上传的文件。

    安全配置：Web服务器或应用程序的不安全配置可能增加文件上传漏洞的风险。


Chanzi-Separator

修复Java中文件上传漏洞需要采取一系列安全措施来确保上传的文件不会对服务器安全造成威胁。以下是一些关键的修复建议：

    使用白名单：仅允许特定类型的文件上传，如图片和文档，并确保这些类型不可能被执行。

    限制文件解析：对于用户上传的文件，再次通过 url 访问该文件时，直接以文件下载方式返回，即使上传了 html、jsp也不进行解析。

    文件类型验证：在服务器端验证文件的MIME类型，确保上传的文件与所声明的类型相符。

    文件扩展名检查：检查文件扩展名是否在允许的列表中，但要注意这并不足以防止攻击，因为扩展名可以被伪造。

    内容检查：对上传的文件进行扫描，查找可能的恶意代码，特别是对于脚本和可执行文件。

    随机重命名文件：更改上传文件的名称，使用随机生成的名称，以防止预期的文件名攻击。

    限制文件大小：设置文件大小限制，防止过大的文件上传消耗服务器资源或利用潜在的漏洞。

    文件上传目录权限：确保文件上传目录不允许执行权限，这样即使上传了脚本文件，也无法被服务器执行。

    使用安全的文件处理库：使用成熟的文件处理库来处理上传的文件，避免自己处理文件上传时可能引入的安全风险。

    前端和后端验证：在前端和后端都进行文件验证，确保即使前端验证被绕过，后端也能提供安全保障。

    避免使用../：确保文件上传路径不包含../，防止攻击者通过路径遍历访问其他目录。

    使用HTTPS：通过使用HTTPS来上传文件，确保文件在传输过程中的安全性，防止中间人攻击。

    错误消息处理：避免在错误消息中显示敏感信息，如文件路径或服务器配置。

Chanzi-Separator
*/