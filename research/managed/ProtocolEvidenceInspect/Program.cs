using System;
using System.IO;
using System.Linq;
using System.Globalization;
using System.Collections.Generic;
using System.Text.Json;
using Mono.Cecil;
public static class ProtocolEvidenceInspect
{
    static string Tok(IMetadataTokenProvider x) => "0x"+x.MetadataToken.ToUInt32().ToString("X8");
    static object Arg(CustomAttributeArgument a) => new { type=a.Type.FullName, value=a.Value is CustomAttributeArgument[] many ? (object)many.Select(Arg).ToArray() : a.Value?.ToString() };
    static object[] Attr(ICustomAttributeProvider p) => p.CustomAttributes.Select(a => (object)new { type=a.AttributeType.FullName, args=a.ConstructorArguments.Select(Arg).ToArray(), fields=a.Fields.Select(x=>new { x.Name,value=Arg(x.Argument) }).ToArray(), properties=a.Properties.Select(x=>new { x.Name,value=Arg(x.Argument) }).ToArray() }).ToArray();
    static IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> ts) { foreach(var t in ts) { yield return t; foreach(var n in Walk(t.NestedTypes)) yield return n; } }
    public static int Main(string[] args)
    {
        using var mod=ModuleDefinition.ReadModule(args[1],new ReaderParameters { ReadingMode=ReadingMode.Deferred });
        var records=new List<object>();
        if(args[0]=="attrs") foreach(var s in args.Skip(3))
        {
            var p=mod.LookupToken(unchecked((int)uint.Parse(s.Replace("0x",""),NumberStyles.HexNumber)));
            if(p is MethodDefinition m) records.Add(new { token=Tok(m), name=m.FullName, attributes=Attr(m), declaring=m.DeclaringType.FullName, typeAttributes=Attr(m.DeclaringType), parameters=m.Parameters.Select(v=>new { v.Name,type=v.ParameterType.FullName }).ToArray() });
            else if(p is TypeDefinition t) records.Add(new { token=Tok(t),name=t.FullName,attributes=Attr(t),fields=t.Fields.Select(f=>new { token=Tok(f),name=f.FullName,attributes=Attr(f) }).ToArray(), methods=t.Methods.Select(v=>new { token=Tok(v), name=v.FullName,attributes=Attr(v) }).ToArray() });
        }
        else if(args[0]=="mentions")
        {
            var names=args.Skip(3).ToArray();
            foreach(var t in Walk(mod.Types))
            {
                var fs=t.Fields.Where(f=>names.Any(n=>f.FieldType.FullName.Contains(n))).Select(f=>new { token=Tok(f),name=f.FullName }).ToArray();
                var ms=t.Methods.Where(m=>names.Any(n=>m.FullName.Contains(n)) && !names.Contains(t.FullName)).Select(m=>new { token=Tok(m),name=m.FullName,attributes=Attr(m) }).ToArray();
                if(fs.Length>0||ms.Length>0) records.Add(new { token=Tok(t),name=t.FullName,fields=fs,methods=ms });
            }
        }
        else if(args[0]=="routes")
        {
            var commands=new HashSet<string>(args.Skip(3));
            foreach(var t in Walk(mod.Types)) foreach(var m in t.Methods)
            {
                foreach(var a in m.CustomAttributes)
                {
                    if(a.AttributeType.Name!="HNMOBHFEEON" || a.ConstructorArguments.Count<2) continue;
                    var command=a.ConstructorArguments[0].Value.ToString();
                    var module=a.ConstructorArguments[1].Value.ToString();
                    if(module=="3" && commands.Contains(command)) records.Add(new { token=Tok(m),name=m.FullName,command,module,attributes=Attr(m) });
                }
            }
        }
        else throw new ArgumentException("mode");
        File.WriteAllText(args[2],JsonSerializer.Serialize(records,new JsonSerializerOptions { WriteIndented=true }));
        Console.WriteLine(JsonSerializer.Serialize(new { mode=args[0],records=records.Count,output=args[2] }));
        return 0;
    }
}
