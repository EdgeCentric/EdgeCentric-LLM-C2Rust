import cpp
 
from DeclarationEntry decl, File f
where decl.getFile() instanceof HeaderFile and 
        (f instanceof CFile or f instanceof CppFile) and
        if decl.getDeclaration() instanceof TypedefType
            then f = decl.getDeclaration().(TypedefType).stripType().getFile()
            else f = decl.getDeclaration().getFile()
select decl.getFile().toString(), f.toString()