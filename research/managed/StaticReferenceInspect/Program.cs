using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Reflection.PortableExecutable;
using Mono.Cecil;
using Mono.Cecil.Cil;

public static class StaticReferenceInspect
{
    static IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types)
    { foreach(var t in types) { yield return t; foreach(var n in Walk(t.NestedTypes)) yield return n; } }
    static string Tok(IMetadataTokenProvider p) => "0x" + p.MetadataToken.ToUInt32().ToString("X8");
    static string Operand(object o)
    {
        if(o is Instruction i) return "IL_"+i.Offset.ToString("X4");
        if(o is Instruction[] a) return string.Join(",",a.Select(x=>"IL_"+x.Offset.ToString("X4")));
        if(o is string s) return JsonSerializer.Serialize(s);
        return o?.ToString() ?? "";
    }
    public static int Main(string[] args)
    {
        if(args.Length<3) throw new ArgumentException("assembly output target-tokens...");
        byte[] image=File.ReadAllBytes(args[0]);
        using var pe=new PEReader(new MemoryStream(image,false));
        using var mod=ModuleDefinition.ReadModule(new MemoryStream(image,false),new ReaderParameters { ReadingMode=ReadingMode.Deferred, ReadSymbols=false });
        Directory.CreateDirectory(args[1]);
        var wanted=new HashSet<string>(StringComparer.Ordinal);
        var tokens=new HashSet<uint>();
        foreach(var arg in args.Skip(2))
        {
            uint id=uint.Parse(arg.Replace("0x",""),NumberStyles.HexNumber);
            var member=(MemberReference)mod.LookupToken(unchecked((int)id));
            wanted.Add(member.FullName); tokens.Add(id);
        }
        foreach(var member in mod.GetMemberReferences())
            if(wanted.Contains(member.FullName)) tokens.Add(member.MetadataToken.ToUInt32());
        var patterns=tokens.Select(BitConverter.GetBytes).ToArray();
        var results=new List<object>();
        int visited=0,prefiltered=0,exported=0;
        foreach(var t in Walk(mod.Types)) foreach(var m in t.Methods)
        {
            if(m.RVA==0 || !m.HasBody) continue;
            visited++; int off=-1;
            foreach(var s in pe.PEHeaders.SectionHeaders)
                if(m.RVA>=s.VirtualAddress && m.RVA-s.VirtualAddress<s.SizeOfRawData) { off=s.PointerToRawData+m.RVA-s.VirtualAddress; break; }
            if(off<0 || off>=image.Length) continue;
            int head,size; int tag=image[off]&3;
            if(tag==2) { head=1; size=image[off]>>2; }
            else if(tag==3 && off<=image.Length-12) { head=(BitConverter.ToUInt16(image,off)>>12)*4; size=BitConverter.ToInt32(image,off+4); }
            else continue;
            if(head<1 || size<0 || (long)off+head+size>image.Length) continue;
            var il=new ReadOnlySpan<byte>(image,off+head,size);
            bool maybe=false; foreach(var p in patterns) if(il.IndexOf(p)>=0) { maybe=true; break; }
            if(!maybe) continue; prefiltered++;
            var hits=new List<object>();
            foreach(var i in m.Body.Instructions)
                if(i.Operand is MemberReference r && wanted.Contains(r.FullName))
                    hits.Add(new { il="IL_"+i.Offset.ToString("X4"),opcode=i.OpCode.Name,target=r.FullName });
            if(hits.Count==0) continue;
            string filename=Tok(m)+".il.txt";
            using(var w=new StreamWriter(Path.Combine(args[1],filename),false,new UTF8Encoding(false)))
            {
                w.WriteLine(m.FullName); w.WriteLine("TOKEN "+Tok(m));
                w.WriteLine("LOCALS "+string.Join("; ",m.Body.Variables.Select(v=>v.Index+":"+v.VariableType.FullName)));
                foreach(var i in m.Body.Instructions) w.WriteLine($"IL_{i.Offset:X4}: {i.OpCode.Name} {Operand(i.Operand)}");
            }
            exported++;
            results.Add(new { token=Tok(m),method=m.FullName,file=filename,hits });
        }
        var report=new { targets=wanted.ToArray(),visited,prefiltered,exported,methods=results };
        File.WriteAllText(Path.Combine(args[1],"references.json"),JsonSerializer.Serialize(report,new JsonSerializerOptions { WriteIndented=true }));
        Console.WriteLine(JsonSerializer.Serialize(new { visited,prefiltered,exported,output=args[1] }));
        return 0;
    }
}
