import cpp
 
from Declaration decl, Location loc
where ((not decl instanceof Function) implies decl.isTopLevel()) and 
    (if decl instanceof Function 
        then loc = decl.getDefinitionLocation()
        else loc = decl.getLocation()) and
    not decl instanceof ClassTemplateInstantiation  and
    not decl instanceof FunctionTemplateInstantiation
select decl.getAPrimaryQlClass(), loc.toString(), decl.getQualifiedName()