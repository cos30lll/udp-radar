using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class StaticAssemblyInspect
{
    static readonly JsonSerializerOptions Json = new JsonSerializerOptions { WriteIndented = true };
    static IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> ts)
    { foreach (var t in ts) { yield return t; foreach (var n in Walk(t.NestedTypes)) yield return n; } }
    static string Token(IMetadataTokenProvider x) => "0x" + x.MetadataToken.ToUInt32().ToString("X8");
    static object Field(FieldDefinition f) => new { token=Token(f), name=f.Name, type=f.FieldType.FullName, attributes=f.Attributes.ToString(), constant=f.HasConstant ? Convert.ToString(f.Constant, System.Globalization.CultureInfo.InvariantCulture) : null };
    static object Method(MethodDefinition m) => new { token=Token(m), name=m.Name, signature=m.FullName, rva=m.RVA, hasBody=m.HasBody, attributes=m.Attributes.ToString(), pinvoke=m.IsPInvokeImpl ? new { module=m.PInvokeInfo.Module.Name, entry=m.PInvokeInfo.EntryPoint } : null };
    static string Operand(object x)
    {
        if (x == null) return "";
        if (x is Instruction i) return "IL_" + i.Offset.ToString("X4");
        if (x is Instruction[] a) return string.Join(",", a.Select(j => "IL_"+j.Offset.ToString("X4")));
        if (x is string s) return JsonSerializer.Serialize(s);
        return x.ToString();
    }
    public static int Main(string[] args)
    {
        if (args.Length < 3) throw new ArgumentException("mode assembly output-directory [tokens-or-exact-type-names]");
        string mode=args[0], output=args[2]; Directory.CreateDirectory(output);
        using var mod=ModuleDefinition.ReadModule(args[1], new ReaderParameters { ReadingMode=ReadingMode.Deferred, ReadSymbols=false });
        var types=Walk(mod.Types).ToArray();
        if (mode == "index")
        {
            var rx=new Regex(@"udp|kcp|enet|network|netclient|netsocket|socket|packet|datagram|encrypt|decrypt|cipher|chacha|handshake|keyexchange|sessionkey|secretkey|diffie|ecdh|sync.*(?:position|move)|(?:position|move).*sync",RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
            var candidates=new List<object>();
            foreach(var t in types)
            {
                var fs=t.Fields.Where(f=>rx.IsMatch(f.Name)).Select(Field).ToArray();
                var ms=t.Methods.Where(m=>rx.IsMatch(m.Name)).Select(Method).ToArray();
                bool named=rx.IsMatch(t.FullName);
                if(named || fs.Length>0 || ms.Length>0) candidates.Add(new { token=Token(t), type=t.FullName, baseType=t.BaseType?.FullName, nameMatch=named, fields=fs, methods=ms, fieldCount=t.Fields.Count, methodCount=t.Methods.Count });
            }
            File.WriteAllText(Path.Combine(output,"candidate-index.json"),JsonSerializer.Serialize(candidates,Json));
            using(var w=new StreamWriter(Path.Combine(output,"type-index.tsv"),false,new UTF8Encoding(false)))
            { w.WriteLine("token\ttype\tbase_type\tfields\tmethods"); foreach(var t in types) w.WriteLine($"{Token(t)}\t{t.FullName}\t{t.BaseType?.FullName}\t{t.Fields.Count}\t{t.Methods.Count}"); }
            var calls=new List<object>();
            var external=new Regex(@"System\.Net\.Sockets|System\.Security\.Cryptography|Kcp|LiteNet|Photon|ENet|ChaCha|BouncyCastle",RegexOptions.IgnoreCase);
            foreach(var t in types) foreach(var m in t.Methods)
            {
                if(!m.HasBody) continue;
                foreach(var i in m.Body.Instructions) if(i.Operand is MethodReference r && (i.OpCode.Code==Code.Call || i.OpCode.Code==Code.Callvirt || i.OpCode.Code==Code.Newobj) && external.IsMatch(r.DeclaringType.FullName))
                    calls.Add(new { caller=m.FullName, callerToken=Token(m), il="IL_"+i.Offset.ToString("X4"), target=r.FullName });
            }
            File.WriteAllText(Path.Combine(output,"network-crypto-calls.json"),JsonSerializer.Serialize(calls,Json));
            Console.WriteLine(JsonSerializer.Serialize(new { assembly=mod.Assembly.Name.FullName, types=types.Length, candidates=candidates.Count, externalCalls=calls.Count, references=mod.AssemblyReferences.Select(r=>r.Name).ToArray(), output }));
        }
        else if(mode == "types")
        {
            var want=new HashSet<string>(args.Skip(3),StringComparer.Ordinal);
            var selected=types.Where(t=>want.Contains(t.FullName)||want.Contains(Token(t))).ToArray();
            var records=selected.Select(t=>new { token=Token(t), type=t.FullName, baseType=t.BaseType?.FullName, interfaces=t.Interfaces.Select(i=>i.InterfaceType.FullName).ToArray(), fields=t.Fields.Select(Field).ToArray(), properties=t.Properties.Select(p=>new {p.Name,type=p.PropertyType.FullName}).ToArray(), methods=t.Methods.Select(Method).ToArray() }).ToArray();
            File.WriteAllText(Path.Combine(output,"selected-types.json"),JsonSerializer.Serialize(records,Json));
            Console.WriteLine(JsonSerializer.Serialize(new { selected=records.Length, types=selected.Select(t=>t.FullName).ToArray(),output }));
        }
        else if(mode == "il")
        {
            var want=new HashSet<string>(args.Skip(3),StringComparer.Ordinal);
            int count=0;
            foreach(var t in types) foreach(var m in t.Methods)
            {
                if(!want.Contains(Token(m)) && !want.Contains(m.FullName)) continue;
                using var w=new StreamWriter(Path.Combine(output,Token(m)+".il.txt"),false,new UTF8Encoding(false));
                w.WriteLine(JsonSerializer.Serialize(Method(m),Json));
                if(m.HasBody)
                {
                    w.WriteLine("LOCALS "+string.Join("; ",m.Body.Variables.Select(v=>v.Index+":"+v.VariableType.FullName)));
                    foreach(var i in m.Body.Instructions) w.WriteLine($"IL_{i.Offset:X4}: {i.OpCode.Name} {Operand(i.Operand)}");
                    foreach(var h in m.Body.ExceptionHandlers) w.WriteLine($"EH {h.HandlerType} try={Operand(h.TryStart)}..{Operand(h.TryEnd)} handler={Operand(h.HandlerStart)}..{Operand(h.HandlerEnd)} type={h.CatchType}");
                }
                count++;
            }
            Console.WriteLine(JsonSerializer.Serialize(new { methods=count,output }));
        }
        else throw new ArgumentException("Unknown mode");
        return 0;
    }
}
