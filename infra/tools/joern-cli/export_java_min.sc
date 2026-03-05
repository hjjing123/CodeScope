// export_java_min.sc
// 导出：File/Method/Call/Var/Lit + 边 IN_FILE/HAS_CALL/CALLS(可选)/ARG/AST(局部可扩)/REF(可选)
// + 语义标签：SpringControllerArg / SinkCmd / SinkSql / SinkSsrf 等
//
// 取参：优先 System.getProperty，其次环境变量
// 用法示例：
//   joern --script export_java_min.sc --param cpgFile=/path/to/cpg.bin --param outDir=out_java
//   joern --script export_java_min.sc --param cpgFile=... --param outDir=... --param ENABLE_CALLS=true --param ENABLE_REF=true --param AST_MODE=local
//
// AST_MODE: "none" | "local" | "wide"
//   - none: 不导 AST
//   - local: 只导 argument.ast 下 Identifier/Literal/Call
//   - wide: 额外导 call.ast 与 argument.inAstMinusLeaf 少量上文结构（仍会控量）
//
// 注意：脚本只导“规则友好子图”，不等于 Joern 全量 CPG（避免 --repr all 的体积/速度/OOM风险）:contentReference[oaicite:2]{index=2}

import better.files._
import io.shiftleft.semanticcpg.language._
import scala.util.Try

@main def main(): Unit = {

  def gp(k: String): Option[String] =
    Option(System.getProperty(k)).orElse(sys.env.get(k)).map(_.trim).filter(_.nonEmpty)

  val cpgFile = gp("cpgFile").getOrElse("")
  val outDir  = gp("outDir").getOrElse("out_neo4j_csv_min_java")

  val ENABLE_CALLS = gp("ENABLE_CALLS").exists(_.equalsIgnoreCase("true"))
  val ENABLE_REF   = gp("ENABLE_REF").exists(_.equalsIgnoreCase("true"))
  val AST_MODE     = gp("AST_MODE").getOrElse("local").toLowerCase // none/local/wide

  if (cpgFile.isEmpty) { println("missing cpgFile"); System.exit(2) }

  // 备注：多数 Joern 版本脚本运行时会自动加载 cpg（你如果需要显式 load，请按你版本调整）
  // e.g. loadCpg(cpgFile)

  val out = File(outDir).createDirectories()

  // ---------------- helpers ----------------
  def esc(s: String): String =
    "\"" + Option(s).getOrElse("").replace("\"", "\"\"").replace("\r\n", "\n") + "\""

  def i(v: Option[Integer]): Int = v.map(_.intValue()).getOrElse(-1)

  def uid(kind: String, file: String, line: Int, col: Int, extra: String): String =
    s"$kind|$file|$line|$col|$extra"

  // ---------------- files ----------------
  def writeHeader(path: File, text: String): Unit = path.writeText(text)

  val nFileH = out / "nodes_File_header.csv"
  val nFileD = out / "nodes_File_data.csv"
  val nMethH = out / "nodes_Method_header.csv"
  val nMethD = out / "nodes_Method_data.csv"
  val nCallH = out / "nodes_Call_header.csv"
  val nCallD = out / "nodes_Call_data.csv"
  val nVarH  = out / "nodes_Var_header.csv"
  val nVarD  = out / "nodes_Var_data.csv"
  val nLitH  = out / "nodes_Lit_header.csv"
  val nLitD  = out / "nodes_Lit_data.csv"

  val eInFileH  = out / "edges_IN_FILE_header.csv"
  val eInFileD  = out / "edges_IN_FILE_data.csv"
  val eHasCallH = out / "edges_HAS_CALL_header.csv"
  val eHasCallD = out / "edges_HAS_CALL_data.csv"
  val eCallsH   = out / "edges_CALLS_header.csv"
  val eCallsD   = out / "edges_CALLS_data.csv"
  val eArgH     = out / "edges_ARG_header.csv"
  val eArgD     = out / "edges_ARG_data.csv"
  val eAstH     = out / "edges_AST_header.csv"
  val eAstD     = out / "edges_AST_data.csv"
  val eRefH     = out / "edges_REF_header.csv"
  val eRefD     = out / "edges_REF_data.csv"

  // headers：直接用 id:ID，避免你后续再 patch :ID（你之前也有类似处理）:contentReference[oaicite:3]{index=3}
  writeHeader(nFileH, "id:ID,kind,name,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nMethH, "id:ID,kind,name,fullName,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nCallH, "id:ID,kind,name,methodFullName,receiverType,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nVarH,  "id:ID,kind,name,varType,file,line:INT,col:INT,code,:LABEL\n")
  writeHeader(nLitH,  "id:ID,kind,litType,file,line:INT,col:INT,code,:LABEL\n")

  writeHeader(eInFileH,  ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eHasCallH, ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eCallsH,   ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eArgH,     ":START_ID,:END_ID,argIndex:INT,:TYPE\n")
  writeHeader(eAstH,     ":START_ID,:END_ID,:TYPE\n")
  writeHeader(eRefH,     ":START_ID,:END_ID,:TYPE\n")

  // ---------------- accumulators ----------------
  val fileRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val methRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val callRows = scala.collection.mutable.LinkedHashMap[String, String]()
  val varRows  = scala.collection.mutable.LinkedHashMap[String, String]()
  val litRows  = scala.collection.mutable.LinkedHashMap[String, String]()

  val eInFile  = scala.collection.mutable.LinkedHashSet[String]()
  val eHasCall = scala.collection.mutable.LinkedHashSet[String]()
  val eCalls   = scala.collection.mutable.LinkedHashSet[String]()
  val eArg     = scala.collection.mutable.LinkedHashSet[String]()
  val eAst     = scala.collection.mutable.LinkedHashSet[String]()
  val eRef     = scala.collection.mutable.LinkedHashSet[String]()

  // ---------------- Java semantics ----------------
  val springAnno = Set("Controller","RestController","RequestMapping","GetMapping","PostMapping","PutMapping","DeleteMapping","PatchMapping")
  def isSpringControllerMethod(m: Method): Boolean =
    Try(m.annotation.name.l.toSet).getOrElse(Set.empty).exists(springAnno.contains)

  val cmdSinks = List(
    "java.lang.Runtime.exec",
    "java.lang.ProcessBuilder.<init>",
    "java.lang.ProcessBuilder.start"
  )
  val sqlSinks = List(
    "java.sql.Statement.execute",
    "java.sql.Statement.executeQuery",
    "java.sql.Statement.executeUpdate",
    "java.sql.PreparedStatement.execute",
    "org.springframework.jdbc.core.JdbcTemplate.query",
    "org.springframework.jdbc.core.JdbcTemplate.update"
  )
  val ssrfSinks = List(
    "java.net.URL.openConnection",
    "java.net.HttpURLConnection.connect",
    "okhttp3.OkHttpClient.newCall"
  )

  def labelForCall(c: Call): Set[String] = {
    val mf = Option(c.methodFullName).getOrElse("")
    val rt = Try(c.receiverTypeFullName).toOption.getOrElse("")
    val labs = scala.collection.mutable.Set("Call")
    if (cmdSinks.exists(mf.startsWith)) labs += "SinkCmd"
    if (sqlSinks.exists(mf.startsWith)) labs += "SinkSql"
    if (ssrfSinks.exists(mf.startsWith)) labs += "SinkSsrf"
    if (mf.startsWith("java.lang.ProcessBuilder") || rt.contains("ProcessBuilder")) labs += "ProcessBuilder"
    labs.toSet
  }

  def labelForParam(p: MethodParameterIn, owner: Method): Set[String] = {
    val labs = scala.collection.mutable.Set("Var","Param")
    if (isSpringControllerMethod(owner)) labs += "SpringControllerArg"
    labs.toSet
  }

  // ---------------- export File ----------------
  cpg.file.l.foreach { f =>
    val fn = Option(f.name).getOrElse("")
    val id = uid("File", fn, -1, -1, fn)
    fileRows.update(id, s"${esc(id)},${esc("File")},${esc(fn)},${esc(fn)},-1,-1,${esc("")},${esc("File")}")
  }

  // ---------------- export Method + IN_FILE ----------------
  cpg.method.l.foreach { m =>
    val mf = Try(m.location.filename).toOption.getOrElse("")
    val line = i(m.lineNumber); val col = i(m.columnNumber)
    val mid  = uid("Method", mf, line, col, m.fullName)

    val mLabs = scala.collection.mutable.Set("Method")
    if (isSpringControllerMethod(m)) mLabs += "SpringController"

    // Method 的 code 建议只放 signature（避免大字段）
    val mCode = Try(m.signature).toOption.getOrElse(m.name)
    methRows.update(mid, s"${esc(mid)},${esc("Method")},${esc(m.name)},${esc(m.fullName)},${esc(mf)},$line,$col,${esc(mCode)},${esc(mLabs.mkString(";"))}")

    val fid = uid("File", mf, -1, -1, mf)
    fileRows.update(fid, s"${esc(fid)},${esc("File")},${esc(mf)},${esc(mf)},-1,-1,${esc("")},${esc("File")}")
    eInFile.add(s"${esc(mid)},${esc(fid)},IN_FILE")

    // 可选：方法间调用 CALLS（解析得到则导）
    if (ENABLE_CALLS) {
      Try(m.callee.l).toOption.getOrElse(Nil).foreach { cal =>
        val cf = Try(cal.location.filename).toOption.getOrElse("")
        val cid = uid("Method", cf, i(cal.lineNumber), i(cal.columnNumber), cal.fullName)
        eCalls.add(s"${esc(mid)},${esc(cid)},CALLS")
      }
    }

    // method 内 callsite
    m.call.l.foreach { c =>
      val cf = Try(c.location.filename).toOption.getOrElse(mf)
      val cl = i(c.lineNumber); val cc = i(c.columnNumber)
      val cid = uid("Call", cf, cl, cc, s"${c.name}|${c.methodFullName}")

      val labs = labelForCall(c).mkString(";")
      val recvType = Try(c.receiverTypeFullName).toOption.getOrElse("")
      callRows.update(cid, s"${esc(cid)},${esc("Call")},${esc(c.name)},${esc(c.methodFullName)},${esc(recvType)},${esc(cf)},$cl,$cc,${esc(c.code)},${esc(labs)}")

      eHasCall.add(s"${esc(mid)},${esc(cid)},HAS_CALL")

      // arguments
      c.argument.l.foreach { a =>
        val af = Try(a.location.filename).toOption.getOrElse(cf)
        val al = i(a.lineNumber); val ac = i(a.columnNumber)
        val argIdx = Try(a.argumentIndex).toOption.getOrElse(-1)

        // 只抽取规则常用的表达式节点：Param / Local/Identifier / Literal / Call
        val (aid, kind, row) = a match {
          case p: MethodParameterIn =>
            val vid = uid("Var", af, al, ac, s"param|${p.name}|${m.fullName}")
            val vlabs = labelForParam(p, m).mkString(";")
            (vid, "Var", s"${esc(vid)},${esc("Var")},${esc(p.name)},${esc(p.typeFullName)},${esc(af)},$al,$ac,${esc(p.code)},${esc(vlabs)}")

          case l: Literal =>
            val lid = uid("Lit", af, al, ac, s"${l.typeFullName}|${l.code}")
            (lid, "Lit", s"${esc(lid)},${esc("Lit")},${esc(l.typeFullName)},${esc(af)},$al,$ac,${esc(l.code)},${esc("Lit")}")

          case idn: Identifier =>
            val vid = uid("Var", af, al, ac, s"id|${idn.name}|${m.fullName}")
            val vlabs = scala.collection.mutable.Set("Var","Identifier")
            valRows.update(vid, "") // placeholder set later

            // 可选：REF 边（Identifier -> Decl），如果你的 front-end 能解析
            if (ENABLE_REF) {
              Try(idn.refsTo.l).toOption.getOrElse(Nil).headOption.foreach { decl =>
                val df = Try(decl.location.filename).toOption.getOrElse(af)
                val dl = i(decl.lineNumber); val dc = i(decl.columnNumber)
                val did = uid("Var", df, dl, dc, s"decl|${decl.name}|${m.fullName}")
                val drow = s"${esc(did)},${esc("Var")},${esc(decl.name)},${esc(decl.typeFullName)},${esc(df)},$dl,$dc,${esc(decl.code)},${esc("Var;Decl")}"
                varRows.update(did, drow)
                eRef.add(s"${esc(vid)},${esc(did)},REF")
              }
            }

            val vrow = s"${esc(vid)},${esc("Var")},${esc(idn.name)},${esc(idn.typeFullName)},${esc(af)},$al,$ac,${esc(idn.code)},${esc(vlabs.mkString(";"))}"
            (vid, "Var", vrow)

          case cc2: Call =>
            val nid = uid("Call", af, al, ac, s"${cc2.name}|${cc2.methodFullName}")
            val nlabs = labelForCall(cc2).mkString(";")
            val r2 = Try(cc2.receiverTypeFullName).toOption.getOrElse("")
            (nid, "Call", s"${esc(nid)},${esc("Call")},${esc(cc2.name)},${esc(cc2.methodFullName)},${esc(r2)},${esc(af)},$al,$ac,${esc(cc2.code)},${esc(nlabs)}")

          case other =>
            val vid = uid("Var", af, al, ac, s"expr|${other.code}|${m.fullName}")
            (vid, "Var", s"${esc(vid)},${esc("Var")},${esc("")},${esc("")},${esc(af)},$al,$ac,${esc(other.code)},${esc("Var;Expr")}")
        }

        kind match {
          case "Var"  => varRows.update(aid, row)
          case "Lit"  => litRows.update(aid, row)
          case "Call" => callRows.update(aid, row)
          case _      => varRows.update(aid, row)
        }

        eArg.add(s"${esc(cid)},${esc(aid)},$argIdx,ARG")

        // AST（可选）
        if (AST_MODE != "none") {
          // local：只扩 argument.ast 下 Identifier/Literal/Call
          val astNodes =
            if (AST_MODE == "wide") Try(a.inAstMinusLeaf.l ++ a.ast.l ++ c.ast.l).toOption.getOrElse(Nil)
            else Try(a.ast.l).toOption.getOrElse(Nil)

          astNodes.foreach {
            case ii: Identifier =>
              val nid = uid("Var", af, i(ii.lineNumber), i(ii.columnNumber), s"id|${ii.name}|${m.fullName}")
              varRows.update(nid, s"${esc(nid)},${esc("Var")},${esc(ii.name)},${esc(ii.typeFullName)},${esc(af)},${i(ii.lineNumber)},${i(ii.columnNumber)},${esc(ii.code)},${esc("Var;Identifier")}")
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case ll: Literal =>
              val nid = uid("Lit", af, i(ll.lineNumber), i(ll.columnNumber), s"${ll.typeFullName}|${ll.code}")
              litRows.update(nid, s"${esc(nid)},${esc("Lit")},${esc(ll.typeFullName)},${esc(af)},${i(ll.lineNumber)},${i(ll.columnNumber)},${esc(ll.code)},${esc("Lit")}")
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case cl: Call =>
              val nid = uid("Call", af, i(cl.lineNumber), i(cl.columnNumber), s"${cl.name}|${cl.methodFullName}")
              val nlabs = labelForCall(cl).mkString(";")
              val r3 = Try(cl.receiverTypeFullName).toOption.getOrElse("")
              callRows.update(nid, s"${esc(nid)},${esc("Call")},${esc(cl.name)},${esc(cl.methodFullName)},${esc(r3)},${esc(af)},${i(cl.lineNumber)},${i(cl.columnNumber)},${esc(cl.code)},${esc(nlabs)}")
              eAst.add(s"${esc(aid)},${esc(nid)},AST")
            case _ => // ignore
          }
        }
      }
    }
  }

  // ---------------- flush ----------------
  nFileD.writeText(fileRows.values.mkString("", "\n", "\n"))
  nMethD.writeText(methRows.values.mkString("", "\n", "\n"))
  nCallD.writeText(callRows.values.mkString("", "\n", "\n"))
  nVarD.writeText(varRows.values.mkString("", "\n", "\n"))
  nLitD.writeText(litRows.values.mkString("", "\n", "\n"))

  eInFileD.writeText(eInFile.mkString("", "\n", "\n"))
  eHasCallD.writeText(eHasCall.mkString("", "\n", "\n"))
  eCallsD.writeText(eCalls.mkString("", "\n", "\n"))
  eArgD.writeText(eArg.mkString("", "\n", "\n"))
  eAstD.writeText(eAst.mkString("", "\n", "\n"))
  eRefD.writeText(eRef.mkString("", "\n", "\n"))

  println(s"[OK] exported to $outDir")
}