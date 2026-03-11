MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
     (
     (LOWER(sinkNode.name) ENDS WITH 'password' AND NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'pass' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'passwd' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'secretkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'apikey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'apitoken' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'accesstoken' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'sessionKey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'encryptionkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'decryptionkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'encryptkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'bearertoken' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'sshkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'jwtsecret' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'jwt.secret' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'jwtkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'presharedkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'privatekey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'private-key' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'admin.key' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'secret.key' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'signkey' AND  NOT LOWER(sinkNode.value) STARTS WITH '${') OR
     (LOWER(sinkNode.name) ENDS WITH 'secret' AND  NOT LOWER(sinkNode.value) STARTS WITH '${')
     )
     AND NOT sinkNode.name CONTAINS ' '
     // 排除 语言文件，比如 messages_zh_CN.properties
     AND NOT sinkNode.fileName STARTS WITH 'messages'
     AND NOT sinkNode.fileName STARTS WITH 'message_'
     AND NOT sinkNode.fileName = 'message.properties'
     AND  NOT sinkNode.value  IN ['true', 'false', '~']
RETURN
  sinkNode AS path

/*
Chanzi-Separator

密钥硬编码

硬编码（Hardcoding）问题是指在代码或配置文件中，将某些敏感信息，比如密码密钥以固定值的形式嵌入到代码中，这种做法可能会导致以下安全风险：

敏感信息泄露：硬编码的敏感信息（如数据库密码、API密钥、私钥等）可能会在代码库中被明文存储，这增加了敏感数据在版本控制系统、错误报告或代码审查中被泄露的风险。

安全漏洞：硬编码的凭证和配置信息可能会成为攻击者的目标，一旦泄露，攻击者可能会利用这些信息来访问或控制系统。

审计和合规性问题：在某些情况下，硬编码的做法可能不符合行业标准或法规要求，导致审计和合规性问题。

Chanzi-Separator



为了避免硬编码带来的问题，最佳实践包括：

秘密管理工具（推荐）：使用秘密管理工具（如HashiCorp Vault、AWS Secrets Manager等）来安全地存储和管理敏感信息。

环境变量：使用环境变量来存储环境特定的配置，这样可以在不同的环境中轻松更改配置，而无需更改代码，即便如此也需要考虑服务器被入侵后环境变量的泄露风险。

服务化配置：通过配置服务器或服务（如Spring Cloud Config、Consul等）来集中管理配置信息，即便如此也建议对配置信息进行加密以避免发生泄露。

代码混淆和加密：对于无法避免的硬编码敏感信息，可以采取代码混淆和加密措施，以提高信息的安全性。

Chanzi-Separator
*/