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
  NOT sourceNode.type  IN ['Long', 'Integer','int','long','boolean','Boolean', 'HttpServletResponse']

MATCH
  (sinkNode)
  WHERE
  // 1. 腾讯云对象存储
  ('uploadFile' IN sinkNode.selectors AND 'COSClient' IN sinkNode.receiverTypes) OR  // COS对象存储
  ('createFile' IN sinkNode.selectors AND 'CfsClient' IN sinkNode.receiverTypes) OR  // CFS文件存储
  // 2. 阿里云对象存储
  ('putObject' IN sinkNode.selectors AND 'OSSClient' IN sinkNode.receiverTypes) OR  // OSS对象存储
  ('putObject' IN sinkNode.selectors AND 'OSS' IN sinkNode.receiverTypes AND sinkNode.argPosition = 2) OR  // OSS对象存储
  ('createFile' IN sinkNode.selectors AND 'NasClient' IN sinkNode.receiverTypes) OR  // NAS文件存储
  // 3. 七牛云对象存储
  ('put' IN sinkNode.selectors AND 'UploadManager' IN sinkNode.receiverTypes) OR
  ('uploadBytes' IN sinkNode.selectors AND 'UploadManager' IN sinkNode.receiverTypes) OR
  // 4. AWS S3
  ('putObject' IN sinkNode.selectors AND 'S3Client' IN sinkNode.receiverTypes) OR
  ('uploadPart' IN sinkNode.selectors AND 'S3Client' IN sinkNode.receiverTypes) OR
  // 5. 微软Azure
  ('createFrom' IN sinkNode.selectors AND 'BlobClient' IN sinkNode.receiverTypes) OR  // Blob存储
  ('upload' IN sinkNode.selectors AND 'FileClient' IN sinkNode.receiverTypes) OR  // File存储
  // 6. 谷歌云GCP
  ('createFrom' IN sinkNode.selectors AND 'Storage' IN sinkNode.receiverTypes) OR
  ('create' IN sinkNode.selectors AND 'Storage' IN sinkNode.receiverTypes) OR
  ('upload' IN sinkNode.selectors AND 'StorageClient' IN sinkNode.receiverTypes) OR
  // 7. 华为云
  ('putObject' IN sinkNode.selectors AND 'ObsClient' IN sinkNode.receiverTypes) OR  // OBS对象存储
  ('createFile' IN sinkNode.selectors AND 'SfsClient' IN sinkNode.receiverTypes) OR  // SFS文件存储
  // 8. 百度智能云
  ('putObject' IN sinkNode.selectors AND 'BosClient' IN sinkNode.receiverTypes) OR  // BOS对象存储
  ('uploadFile' IN sinkNode.selectors AND 'BosClient' IN sinkNode.receiverTypes) OR
  // 9. 金山云
  ('putObject' IN sinkNode.selectors AND 'KsyunClient' IN sinkNode.receiverTypes) OR  // KS3对象存储
  // 10. UCloud
  ('putObject' IN sinkNode.selectors AND 'UcloudClient' IN sinkNode.receiverTypes) OR  // UFile对象存储
  // 11. 私有兼容S3存储（MinIO/阿里云OSS兼容模式）
  ('putObject' IN sinkNode.selectors AND 'MinioClient' IN sinkNode.receiverTypes) OR
  ('uploadObject' IN sinkNode.selectors AND 'MinioClient' IN sinkNode.receiverTypes)

  MATCH
p = shortestPath((sourceNode)- [ * ..30] - >(sinkNode))

RETURN
  p AS path

/*
Chanzi-Separator

对象存储文件上传漏洞

对象存储服务（Object Storage Service）是一种存储大量数据的方法，它允许通过网络访问和管理数据。与传统的文件系统存储不同，对象存储将数据封装在“对象”中，每个对象包含数据和元数据（如名称、创建日期等）。对象存储服务通常由第三方提供，如Amazon S3、Google Cloud Storage和Microsoft Azure Blob Storage，它们提供可扩展性、持久性和高可用性。

在实现文件上传到对象存储的功能时，主要的安全风险为，如果从用户那里直接接收文件名或其他输入，并且未经适当的清理就存储在对象存储中，攻击者可能会注入恶意脚本。

其他可能会遇到的安全问题：

未经授权的访问：如果访问密钥（如AWS的Access Key ID和Secret Access Key）被泄露或未经授权地使用，攻击者可能会访问或修改存储的数据。

数据泄露：如果敏感数据未经加密就存储在对象存储中，攻击者可能会通过未授权访问来窃取这些数据。

跨站点脚本攻击（XSS）：如果从用户那里直接接收文件名或其他输入，并且未经适当的清理就存储在对象存储中，攻击者可能会注入恶意脚本。

服务拒绝（DoS）：攻击者可能会通过上传大量数据或请求来消耗对象存储服务的资源，导致服务不可用。

数据篡改：如果上传的数据在传输过程中未经加密，攻击者可能会在数据传输过程中篡改数据。

不正确的访问控制：如果对象存储的访问控制配置不当，可能会导致数据被未经授权的用户访问。

Chanzi-Separator

为了解决这些安全问题，可以采取以下措施：

使用强身份验证和授权机制：确保只有授权用户才能上传或访问对象存储服务及存储的文件。

加密数据：在数据上传之前对其进行加密，确保即使数据被未授权访问，也无法被读取。

限制上传大小和速率：防止DoS攻击，通过限制单个用户或IP的上传大小和速率。

清理和验证用户输入：确保所有用户输入都经过清理和验证，以防止XSS攻击，通常需要对文件类型、扩展名、内容、大小等进行校验。

定期审计和监控：定期审计对象存储的访问和使用情况，监控异常行为。

Chanzi-Separator
*/