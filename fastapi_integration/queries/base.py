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


class SignalMixin:

    @classmethod
    async def _pre_save(cls, db_session: AsyncSession, instance=None, **kwargs):
        _instance = await cls.pre_save(db_session, instance=instance, **kwargs)
        if _instance is not None:
            return _instance
        else:
            return instance

    @classmethod
    async def _pre_update(cls, db_session: AsyncSession, stmt=None, **kwargs) -> TypedReturnsRows:
        _stmt = await cls.pre_update(db_session, stmt=stmt, **kwargs)
        if _stmt is not None:
            return _stmt
        else:
            return stmt

    @classmethod
    async def _pre_delete(cls, db_session: AsyncSession, stmt=None, **kwargs) -> TypedReturnsRows:
        _stmt = await cls.pre_delete(db_session, stmt=stmt, **kwargs)
        if _stmt is not None:
            return _stmt
        else:
            return stmt

    @classmethod
    async def pre_save(cls, db_session: AsyncSession, instance, **kwargs):
        pass

    @classmethod
    async def pre_update(cls, db_session: AsyncSession, stmt=None, **kwargs):
        pass

    @classmethod
    async def pre_delete(cls, db_session: AsyncSession, stmt=None, **kwargs):
        pass



class QueryMixin(SignalMixin):
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



    @classmethod
    async def apply_filter_type(cls, filter_type: str, conditions: list, column, value) -> list:
        conditions.append(cls.condition_map.get(filter_type, lambda column, value: column == value)(column, value))
        return conditions




    @classmethod
    def _apply_ordering(cls, stmt, order_by: Union[str, Tuple[str]]) -> None:
        if isinstance(order_by, str):
            order_by = (order_by,)

        order_by_columns = []
        for column_name in order_by:
            descending = False
            if column_name.startswith("-"):
                descending = True
                column_name = column_name[1:]

            column = getattr(cls, column_name)
            if descending:
                column = column.desc()
            else:
                column = column.asc()

            order_by_columns.append(column)

        stmt = stmt.order_by(*order_by_columns)
        return stmt



    @classmethod
    async def _build_query(cls, joins=None, order_by=None, skip:int=None, limit:int=None, **kwargs) -> TypedReturnsRows:
        stmt = select(cls)

        if joins is None:
            joins = []

        for related_model in joins:
            stmt = stmt.join(related_model)

        conditions = []
        for key, value in kwargs.items():
            
            filter_parts = key.split('__')
            column_name = filter_parts[0]
            filter_type = filter_parts[1] if len(filter_parts) > 1 else None
            
            related_model = next((join_model for join_model in joins if join_model.__name__.lower() == column_name.lower()), None)
            if related_model is None and column_name:
                if hasattr(cls, column_name):
                    related_model = cls

            
            if related_model is not None:
                filter_field = next((column_name for obj in filter_parts if hasattr(related_model, obj)), None)
                if filter_field == None:
                    raise ValueError("This Column does exists")
                column = getattr(related_model, filter_field)
                conditions = await cls.apply_filter_type(filter_type, conditions, column, value)


        if conditions:
            stmt = stmt.where(and_(*conditions))

        if order_by:
            stmt = cls._apply_ordering(stmt, order_by)
        
        if skip:
            stmt = stmt.offset(skip)

        if limit:
            stmt = stmt.limit(limit)

        return stmt

    


    @classmethod
    async def build_handler(cls, joins=None, order_by=None, skip: int = 0, limit: int = 20, **kwargs) -> TypedReturnsRows:
        cached_query = await cls._build_query(joins, skip=skip, limit=limit, **kwargs)
        return cached_query


    @classmethod
    async def get(cls, db_session: AsyncSession, joins=None, order_by=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await cls.build_handler(joins=joins, order_by=order_by, **kwargs)
        result = await db_session.execute(stmt)
        instance = result.scalars().first()
        return instance

    @classmethod
    async def filter(cls, db_session: AsyncSession, joins=None, order_by=None, skip: int = 0, limit: int = 20, get_count=False, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await cls.build_handler(joins=joins, order_by=order_by, skip=skip, limit=limit, **kwargs)
        result = await db_session.execute(stmt)
        instances = result.scalars().all()

        if not get_count:
            return instances
        
        else:
            stmt = await cls.build_handler(joins=joins, order_by=order_by, **kwargs)
            count = await cls.count(db_session, stmt)
            return (instances, count)


    @classmethod
    async def count(cls, db_session: AsyncSession, stmt) -> int:
        stmt = stmt.with_only_columns(func.count(cls.id))
        result = await db_session.execute(stmt)
        return result.scalar()

    @classmethod
    async def create(cls, db_session: AsyncSession, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        instance = cls(**kwargs)
        instance = await cls._pre_save(db_session, instance, **kwargs)
        try:
            db_session.add(instance)
            await db_session.flush()
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            raise e
        return instance



    @classmethod
    async def all(cls, db_session: AsyncSession, joins=None, order_by=None, skip: int = 0, limit: int = 20, get_count=False) -> Union[Type[Any], Type["QueryMixin"]]:
        return await cls.filter(db_session, joins, order_by=None, skip=0, limit=None)



    @classmethod
    async def delete(cls, db_session: AsyncSession, joins=None, **kwargs) -> int:
        stmt = await cls.build_handler(joins=joins, **kwargs)
        stmt = await cls._pre_delete(db_session, stmt, **kwargs)
        delete_stmt = sqla_delete(cls).where(stmt.whereclause)
        result = await db_session.execute(delete_stmt)
        await db_session.commit()
        return result.rowcount



    @classmethod
    async def update(cls, db_session: AsyncSession, data: dict, joins=None, **kwargs) -> int:
        stmt = await cls.build_handler(joins=joins, **kwargs)
        stmt = await cls._pre_update(db_session, stmt,  **kwargs)
        update_stmt = sqla_update(cls).where(stmt.whereclause).values(data)
        result = await db_session.execute(update_stmt)
        await db_session.commit()
        if result.rowcount == 1:
            updated_instance = await cls.get(db_session, **kwargs)
            return updated_instance
        
        else:
            return result.rowcount or None


    @classmethod
    async def aggregate(cls, db_session: AsyncSession, field: str, agg_func: str = "sum", joins=None, **kwargs) -> Union[int, float, None]:
        if agg_func.lower() == "sum":
            aggregation = func.sum(getattr(cls, field))
        else:
            raise NotImplementedError(f"Unsupported aggregation function '{agg_func}'")

        stmt = await cls.build_handler(joins=joins, **kwargs)
        stmt = stmt.select_from(cls).with_only_columns(aggregation)
        result = await db_session.execute(stmt)
        return result.scalar()