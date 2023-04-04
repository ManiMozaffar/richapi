from sqlalchemy import (
    select,
    and_,
    delete as sqla_delete,
    Column,
    Integer,
    String,
    update as sqla_update,
)
from sqlalchemy.sql.selectable import Self, TypedReturnsRows
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type, Union, Tuple, Any
from sqlalchemy import func, or_
import logging
from sqlalchemy.orm import RelationshipProperty
from .utils import has_endpoint


class BaseQuery:
    def __init__(self, cls):
        self.cls = cls



class SignalMixin(BaseQuery):

    async def _pre_save(self, db_session: AsyncSession, instance=None, **kwargs):
        _instance = await self.pre_save(db_session, instance=instance, **kwargs)
        if _instance is not None:
            return _instance
        else:
            return instance

    async def _pre_update(self, db_session: AsyncSession, stmt=None, **kwargs) -> TypedReturnsRows:
        _stmt = await self.pre_update(db_session, stmt=stmt, **kwargs)
        if _stmt is not None:
            return _stmt
        else:
            return stmt

    async def _pre_delete(self, db_session: AsyncSession, stmt=None, **kwargs) -> TypedReturnsRows:
        _stmt = await self.pre_delete(db_session, stmt=stmt, **kwargs)
        if _stmt is not None:
            return _stmt
        else:
            return stmt

    async def pre_save(self, db_session: AsyncSession, **kwargs):
        pass

    async def pre_update(self, db_session: AsyncSession, stmt=None, **kwargs):
        pass

    async def pre_delete(self, db_session: AsyncSession, stmt=None, **kwargs):
        pass


class QueryMixin(SignalMixin):
    joint:list = []


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

    async def apply_filter_type(self, filter_type: str, conditions: list, column, value) -> list:
        conditions.append(self.condition_map.get(filter_type, lambda column, value: column == value)(column, value))
        return conditions


    def _apply_ordering(self, stmt, order_by: Union[str, Tuple[str]]) -> None:
        """
        Apply ordering to the SQL statement based on the given order_by parameter.

        :param stmt: The SQL statement to modify.
        :param order_by: A string or tuple of strings indicating the columns to order by.
        :return: None
        """
        stmt = stmt.order_by(*[getattr(self.cls, col.lstrip("-")).desc() if col.startswith("-") else getattr(self.cls, col).asc() for col in (order_by if isinstance(order_by, tuple) else (order_by,))])
        return stmt


    
    async def _build_query(self, db_session: AsyncSession, joins: set = set(), order_by=None, skip: int = None, limit: int = None, distinct_fields=None, where=None, select_models=None, **kwargs) -> TypedReturnsRows:
        """
        Build a basic query for the current model.
        :param db_session: The async database session.
        :return: A query object.
        """
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
            self.joint.append(related_model)


        conditions = []
        for key, value in kwargs.items():
            filter_parts = key.split('__')
            column_name = filter_parts[0]
            filter_type = filter_parts[1] if len(filter_parts) > 1 else None

            if column_name and hasattr(self.cls, column_name):
                if isinstance((getattr(self.cls, column_name).property), RelationshipProperty):
                    parent_cls = getattr(self.cls, column_name).property.mapper.class_
                    if parent_cls not in self.joint:
                        stmt = stmt.join(parent_cls)
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



    async def get(self, db_session: AsyncSession, joins=set(), order_by=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, **kwargs)
        result = await db_session.execute(stmt)
        instance = result.scalars().first()
        return instance


    async def filter(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0, limit: int = 20, get_count=False, 
                    values_fields:list = [], where=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:

        stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, skip=skip, limit=limit, where=where, **kwargs)

        if values_fields:
            stmt = stmt.with_only_columns(*[getattr(self.cls, field) for field in values_fields])


        result = await db_session.execute(stmt)
        if self.needs_scalar:
            instances = result.scalars().all()
        else:
            instances = result.all()

        if not get_count:
            return instances

        else:
            stmt = await self.build_handler(db_session, joins=joins, order_by=order_by, **kwargs)
            count = await self.count(db_session, stmt)
            return (instances, count)




    async def count(self, db_session: AsyncSession, stmt) -> int:
        stmt = stmt.with_only_columns(func.count(self.cls.id))
        result = await db_session.execute(stmt)
        return result.scalar()

    async def create(self, db_session: AsyncSession, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        instance = self.cls()
        for key, value in kwargs.items():
            attr = getattr(self.cls, key, None)

            if attr is None:
                raise ValueError(f"Attribute '{key}' not found in class '{self.cls.__name__}'")
            if hasattr(attr, "property") and isinstance(attr.property, RelationshipProperty):
                related_instance = value
                setattr(instance, key, related_instance)
            else:
                setattr(instance, key, value)

        # instance = await self._pre_save(db_session, instance, **kwargs)
        try:
            db_session.add(instance)
            await db_session.flush()
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            raise e
        return instance


    async def all(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0, limit: int = 20, get_count=False) -> Union[Type[Any], Type["QueryMixin"]]:
        return await self.filter(db_session, joins, order_by=None, skip=0, limit=None)
    

    async def delete(self, db_session: AsyncSession, joins=set(), **kwargs) -> int:
        """
        Delete instances matching the given filters.
        :param db_session: The async database session.
        :param kwargs: Filters for the instances to delete.
        :return: None
        """
        stmt = await self.build_handler(db_session=db_session, joins=joins, **kwargs)
        stmt = await self._pre_delete(db_session, stmt, **kwargs)
        delete_stmt = sqla_delete(self.cls).where(stmt.whereclause)
        result = await db_session.execute(delete_stmt)
        await db_session.commit()
        return result.rowcount


    async def update(self, db_session: AsyncSession, data: dict, joins=set(), **kwargs) -> int:
        """
        Update instances matching the given filters with the given data.

        :param db_session: The async database session.
        :param update_data: A dictionary containing the data to update.
        :param kwargs: Filters for the instances to update.
        :return: None
        """
        stmt = await self.build_handler(db_session=db_session, joins=joins, **kwargs)
        stmt = await self._pre_update(db_session, stmt, **kwargs)
        update_stmt = sqla_update(self.cls).where(stmt.whereclause).values(data)
        result = await db_session.execute(update_stmt)
        await db_session.commit()
        if result.rowcount == 1:
            updated_instance = await self.get(db_session, **kwargs)
            return updated_instance
        else:
            return result.rowcount or None
    

    async def aggregate(self, db_session: AsyncSession, field: str, agg_func: str = "sum", joins=set(), **kwargs) -> Union[int, float, None]:
        """
        Perform an aggregation on a column.

        :param db_session: The async database session.
        :param aggregation_fn: The aggregation function to use.
        :param column: The column to aggregate.
        :param kwargs: Additional filters for the query.
        :return: The result of the aggregation.
        """
        supported_agg_funcs = {
            "sum": func.sum,
            "count": func.count,
            "avg": func.avg,
            "min": func.min,
            "max": func.max
        }
        if agg_func.lower() not in supported_agg_funcs:
            raise NotImplementedError(f"Unsupported aggregation function '{agg_func}'")
        
        aggregation = supported_agg_funcs[agg_func.lower()](getattr(self.cls, field))
        stmt = select(aggregation)

        stmt = await self.build_handler(joins=joins, **kwargs)
        stmt = stmt.select_from(self.cls).with_only_columns(aggregation)
        result = await db_session.execute(stmt)
        return result.scalar()
        

    

    async def exclude(self, db_session: AsyncSession, joins=set(), order_by=None, skip: int = 0,  get_count=False, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        """
        Retrieve instances that do not match the given filters.

        :param db_session: The async database session.
        :param joins: A set of join conditions.
        :param order_by: A string or tuple of strings indicating the columns to order by.
        :param skip: The number of instances to skip.
        :param limit: The maximum number of instances to return.
        :param get_count: If True, also return the count of instances.
        :param kwargs: Additional filters for the query.
        :return: A list of instances or a tuple containing the list of instances and the count.
        """
        all_stmt = await self.build_handler(db_session=db_session, joins=joins, order_by=order_by, skip=skip, limit=None)
        all_result = await db_session.execute(all_stmt)
        all_instances = all_result.scalars().all()
        exclude_stmt = await self.build_handler(db_session=db_session, joins=joins, order_by=order_by, skip=skip, limit=None, **kwargs)    
        exclude_result = await db_session.execute(exclude_stmt)
        exclude_instances = exclude_result.scalars().all()
        instances = list(set(all_instances) - set(exclude_instances))
        if not get_count:
            return instances
        else:
            count = len(instances)
            return (instances, count)




    def _apply_distinct(self, stmt, distinct_fields=None):
        """
        Apply a DISTINCT clause to the SQL statement.

        :param stmt: The SQL statement to modify.
        :return: None
        """
        if distinct_fields:
            if not isinstance(distinct_fields, (list, tuple)):
                distinct_fields = [distinct_fields]

            columns = [getattr(self.cls, field) for field in distinct_fields]
            stmt = stmt.distinct(*columns)
        return stmt