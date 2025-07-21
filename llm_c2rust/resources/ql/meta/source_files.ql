import cpp

from File f
where f instanceof CFile or f instanceof CppFile
select f.toString(), f.getAPrimaryQlClass()