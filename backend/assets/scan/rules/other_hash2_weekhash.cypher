// 请求数据 流向 md5 DigestUtils.md5Hex(originalString);
// DigestUtils.sha1Hex(data);
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
  ('md5Hex' IN sinkNode.selectors AND 'DigestUtils' IN sinkNode.receivers) OR
  ('sha1Hex' IN sinkNode.selectors AND 'DigestUtils' IN sinkNode.receivers)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

弱哈希算法

弱hash指的是那些在安全性上存在缺陷，容易被破解或者碰撞的哈希算法。这些算法在设计时可能没有考虑到足够的安全因素，或者随着计算技术的发展，原本认为安全的算法已经不再安全。弱哈希算法的主要问题在于它们不能提供足够的抗碰撞性、抗第一原象性和抗第二原象性，这些是密码学中哈希函数的重要安全性质。

弱哈希算法的种类：

MD2、MD4、MD5：这些算法在密码学中曾经广泛使用，但由于存在根本性的缺陷，现在已经不推荐用于安全性关键的上下文。例如，MD5算法在1991年被设计出来时，被认为是非常安全的，但随后黑客发现了如何快速解码这个算法的方法。

RIPEMD-160：虽然一度被认为非常安全，但由于有效破解MD和RIPEMD散列的技术已广泛使用，不应依赖这些算法来保证安全性。

SHA-1：尽管破坏SHA-1的技术仍需要极高的计算能力，但攻击者已经发现了该算法的致命弱点，破坏它的技术可能会导致更快地发起攻击。

安全风险：

使用弱哈希算法会带来以下安全风险：

数据完整性无法保证：攻击者可能会找到两个不同的输入，它们的哈希值相同，从而绕过基于哈希的数据完整性检查。

数据泄露：如果使用弱哈希算法存储密码或其他敏感信息，攻击者可能通过彩虹表攻击或其他方法逆向破解哈希值，获取原始数据。

身份伪造：在数字签名等场景中，如果哈希算法不抗第二原象性，攻击者可能找到不同的输入产生相同的哈希值，从而伪造身份。

中间人攻击：在SSL/TLS等协议中，如果使用弱加密算法，攻击者可能迫使服务器和用户之间使用低强度的加密方式，然后通过暴力破解，窃取传输内容。

Chanzi-Separator

弱哈希算法的整改方案通常包括以下几个步骤：

升级算法：替换现有的弱哈希算法，如MD5、SHA-1等，使用更安全的哈希算法，如SHA-256、SHA-3等。这些算法在设计上更加复杂，提供了更高的安全性，能够有效抵抗已知的攻击方法。

增加盐值：对于密码存储等场景，可以通过添加随机生成的盐值（salt）来增强哈希的安全性。盐值是一个随机数，与密码一起哈希，以防止使用彩虹表等方法进行逆向破解。

使用密钥：在哈希过程中使用密钥，这样即使攻击者知道哈希算法，没有密钥也无法生成有效的哈希值，这增加了破解的难度。

性能与安全性的平衡：在选择哈希算法时，需要综合考虑安全性、性能和应用场景等因素。对于需要高安全性的场景，推荐使用SHA-256或SHA-3。

系统兼容性：在更换哈希算法时，需要确保新算法与现有系统的兼容性，以避免系统中断或数据丢失。

在不同的场景下，推荐的哈希算法可能不同：

数据完整性验证：可以使用SHA-256或SHA-3，这些算法提供了较强的抗碰撞性，适合用于确保数据在传输过程中未被篡改。

密码存储：推荐使用SHA-256或SHA-3，并结合盐值和密钥，以提供更高的安全性。

数字签名：在数字签名中，可以使用SHA-256或SHA-3，这些算法在安全性方面表现出色，能够有效抵抗已知的攻击方法。

性能要求高的场景：如果对计算速度有较高要求，可以选择SHA-256或SHA-512，这些算法在处理大块数据时表现出色。

存储和传输成本敏感的场景：如果存储和传输资源有限，可以考虑使用较短的哈希值，如SHA-256，但需确保安全性需求得到满足。

保存用户密码时，推荐使用专门为密码存储设计的哈希算法，因为这些算法通常提供了额外的安全特性，如内置的盐值和密钥派生功能，以抵御暴力破解和彩虹表攻击。以下是几种广泛认为安全的算法：

Argon2：在2015年密码学竞赛中胜出的算法，被NIST认定为最好的密码哈希算法。Argon2设计了三种变体以应对不同的攻击向量，包括Argon2d（针对并行硬件攻击）、Argon2i（针对时间侧信道攻击）和Argon2id（结合了Argon2d和Argon2i的特点）。

bcrypt：这是一个专为密码存储设计的算法，提供了内置的盐值和可调的工作因子（迭代次数），以适应未来的计算能力提升，保持破解难度。

PBKDF2（Password-Based Key Derivation Function 2）：这是一种基于密码的密钥派生函数，提供了高度可定制的参数，如迭代次数和密钥长度，适用于需要平衡安全与性能的应用。

SHA-256 和 SHA-512：虽然这些算法本身不是专为密码存储设计的，但它们提供了较高的安全性，尤其是SHA-512，它提供了更高的抗碰撞性和抗暴力破解能力。

在实际应用中，应该避免使用如MD5和SHA-1这样的老旧算法，因为它们已被证明存在安全隐患，容易发生碰撞攻击。

此外，对于密码存储，除了选择合适的哈希算法外，还应该为每个用户密码生成一个唯一的随机盐值，并且确保哈希过程足够慢，以增加破解的难度。

Dropbox等大公司在存储用户密码时，会采用多层加密策略，如首先使用SHA-512，然后使用Bcrypt算法，并可能进一步使用AES加密。

这样的多层防护策略可以提供更强的安全保障。

总之，整改弱哈希算法的关键在于选择一个在安全性和性能之间取得平衡的强哈希算法，并采取适当的安全措施来保护数据。

Chanzi-Separator
*/