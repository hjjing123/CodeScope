MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
(
sinkNode.nameLower ENDS WITH 'password' OR
sinkNode.nameLower ENDS WITH 'pass' OR
sinkNode.nameLower ENDS WITH 'passwd'  OR
sinkNode.nameLower ENDS WITH 'secretkey' OR
sinkNode.nameLower ENDS WITH 'apikey'  OR
sinkNode.nameLower ENDS WITH 'apitoken'  OR
sinkNode.nameLower ENDS WITH 'accesstoken'  OR
sinkNode.nameLower ENDS WITH 'sessionKey'  OR
sinkNode.nameLower ENDS WITH 'encryptionkey'  OR
sinkNode.nameLower ENDS WITH 'decryptionkey'  OR
sinkNode.nameLower ENDS WITH 'bearertoken'  OR
sinkNode.nameLower ENDS WITH 'sshkey'  OR
sinkNode.nameLower ENDS WITH 'jwtsecret'  OR
sinkNode.nameLower ENDS WITH 'presharedkey'  OR
sinkNode.nameLower ENDS WITH 'privatekey'  OR
sinkNode.nameLower ENDS WITH 'admin.key'  OR
sinkNode.nameLower ENDS WITH 'secret.key'  OR
sinkNode.nameLower ENDS WITH 'secret'
) AND  sinkNode.value IN
// 高频弱口令
['123456','1234', 'root', 'admin', '12345678', 'password', "passwd", "1234abcd", "test", "1111", "root123", "root1234", "admin123", "1qaz2wsx", "1qaz!QAZ", "asdf", "nacos",
'12345', '123', '000000', '666666', '888888', '999999',  // 纯数字弱口令
'123123', '123321', '654321',  // 数字序列弱口令
'user', 'guest', 'default', 'system', 'service',  // 通用弱口令
'123abc', 'abc123', 'abcdef',  // 数字字母简单组合
'admin888', 'admin1234', 'root888',  // 管理员常见弱口令
'mysql', 'oracle', 'redis', 'mongodb',  // 数据库默认弱口令
'']  // 空口令（绝对弱口令）

RETURN
  sinkNode AS path

/*
Chanzi-Separator

弱口令

弱口令是指那些容易被猜测或破解的密码，通常是因为它们过于简单、常见或者缺乏足够的随机性和复杂性。弱口令是网络安全中的一个常见问题，因为它们为攻击者提供了相对容易的入侵途径。以下是弱口令可能引发的一些安全问题：

账户被破解：弱口令很容易被攻击者通过猜测、字典攻击或暴力破解等手段破解，导致账户被非法访问。

数据泄露：一旦攻击者获得账户访问权限，他们可以访问、修改或删除敏感数据，造成数据泄露。

身份盗用：攻击者可能会冒用用户身份进行欺诈活动，损害用户声誉和财产安全。

系统被控制：攻击者可能会利用账户权限执行恶意操作，如安装恶意软件、发起网络攻击或创建僵尸网络。

内部安全威胁：如果内部员工使用弱口令，那么即使没有外部攻击，数据和系统的安全性也难以保障。

合规性问题：许多行业标准和法规要求企业采取合理的安全措施来保护数据，包括使用强口令政策，弱口令的使用可能导致合规性问题。

Chanzi-Separator

为了减少弱口令带来的安全风险，建议实施强口令政策，要求密码必须包含一定长度、大小写字母、数字和特殊字符的组合，同时避免使用公司名称、产品名称、键盘连续字符串等容易被猜测的口令。

Chanzi-Separator
*/
