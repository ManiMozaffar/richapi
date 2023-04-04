from sqlalchemy import func
from sqlalchemy import (
    select,
    and_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import TypedReturnsRows
from sqlalchemy.orm import RelationshipProperty



class BaseQuery:
    needs_scalar: bool = True
    _instance = None

    def __init__(self, cls):
        self.cls = cls


    @property
    def instance(self):
        return self._instance
    

    @instance.setter
    def instance(self, value):
        self._instance = value


    condition_map = {
        'exact': lambda column, value: column == value,
        'contains': lambda column, value: column.contains(value),
        'in': lambda column, value: column.in_(value),
        'gt': lambda column, value: column > value,
        'gte': lambda column, value: column >= value,
        'lt': lambda column, value: column < value,
        'lte': lambda column, value: column <= value,
        'startswith': lambda column, value: column.startswith(value),
        'endswith': lambda column, value: column.endswith(value),
        'range': lambda column, value: column.between(value[0], value[1]),
        'date': lambda column, value: func.date(column) == value,
        'year': lambda column, value: func.extract('year', column) == value,
        'month': lambda column, value: func.extract('month', column) == value,
        'day': lambda column, value: func.extract('day', column) == value,

        'iexact': lambda column, value: column.ilike(value),
        'icontains': lambda column, value: column.ilike(f"%{value}%"),
        'istartswith': lambda column, value: column.ilike(f"{value}%"),
        'iendswith': lambda column, value: column.ilike(f"%{value}"),
    }




    async def _build_query(self, db_session: AsyncSession, joins: set = set(), order_by=None, skip: int = None, limit: int = None, distinct_fields=None, where=None, select_models=None, **kwargs) -> TypedReturnsRows:
        """
        Build a basic query for the current model.
        :param db_session: The async database session.
        :return: A query object.
        """
        joint = list()
        if select_models is not None:
            stmt = select(*select_models, self.cls).select_from(self.cls)
            self.needs_scalar = False
        else:
            stmt = select(self.cls)
            self.needs_scalar = True


        if where is not None:
            stmt = stmt.where(*where)



        for join_condition in joins:
            related_model = join_condition.left.table if join_condition.left.table != self.cls.__table__ else join_condition.right.table
            stmt = stmt.join(related_model, join_condition)
            joint.append(related_model)


        conditions = []
        for key, value in kwargs.items():
            filter_parts = key.split('__')
            column_name = filter_parts[0]
            filter_type = filter_parts[-1] if len(filter_parts) > 1 else None

            if column_name and hasattr(self.cls, column_name):
                if isinstance((getattr(self.cls, column_name).property), RelationshipProperty):
                    parent_cls = getattr(self.cls, column_name).property.mapper.class_
                    if parent_cls not in joint:
                        stmt = stmt.join(parent_cls)
                        joint.append(parent_cls)
                else:
                    parent_cls = self.cls


                filter_field = next((obj for obj in filter_parts if hasattr(parent_cls, obj)), None)
                if filter_field is None:
                    raise ValueError("This Column does not exist")
                column = getattr(parent_cls, filter_field)
                conditions = await self.apply_filter_type(filter_type, conditions, column, value)

    
        if conditions:
            stmt = stmt.where(and_(*conditions))


        if order_by:
            stmt = self._apply_ordering(stmt, order_by)
            stmt = self._apply_distinct(stmt, distinct_fields)
        
        elif distinct_fields:
            raise ValueError("You must specify order_by when using distinct_fields")

        if skip:
            stmt = stmt.offset(skip)

        if limit:
            stmt = stmt.limit(limit)

        return stmt


    async def build_handler(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0, limit: int = 20, distinct_fields=None,  where=None, 
                            select_models=None, **kwargs) -> TypedReturnsRows:
        """
        Build a query handler with the given filters.

        :param db_session: The async database session.
        :param kwargs: Filters for the query.
        :return: A query handler.
        """
        cached_query = await self._build_query(db_session, joins, skip=skip, limit=limit, order_by=order_by, distinct_fields=distinct_fields,  where=where, 
                                            select_models=select_models, **kwargs)
        return cached_query

