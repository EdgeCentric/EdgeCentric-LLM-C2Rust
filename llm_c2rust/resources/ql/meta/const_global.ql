import cpp

from GlobalOrNamespaceVariable v
where v.isConst()
select v.getLocation().toString(), v.getQualifiedName()