from sqlalchemy import (
    select,
    and_,
    delete as sqla_delete,
    Column,
    Integer,
    String,
    update as sqla_update,
)
from sqlalchemy.sql.selectable import Self
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type, Union, Tuple, Any
from sqlalchemy import func, or_



class SignalMixin:

    @classmethod
    async def _pre_save(cls, db_session: AsyncSession, instance=None, **kwargs):
        _instance = await cls.pre_save(db_session, instance=instance, **kwargs)
        if _instance is not None:
            return _instance
        else:
            return instance
        
        
    @classmethod
    async def _pre_update(cls, db_session: AsyncSession, stmt=None, **kwargs):
        _stmt = await cls.pre_update(db_session, stmt=stmt, **kwargs)
        if _stmt is not None:
            return _stmt
        else:
            return stmt

    @classmethod
    async def _pre_delete(cls, db_session: AsyncSession, stmt=None, **kwargs):
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
    async def _build_query(cls, joins=None, order_by=None, skip:int=None, limit:int=None, **kwargs) -> Self:
        stmt = select(cls)

        if joins is None:
            joins = []

        for related_model in joins:
            stmt = stmt.join(related_model)

        conditions = []
        for key, value in kwargs.items():
            if '__' in key:
                relationship_name, attribute_name = key.split('__')
                related_model = None
                for join_model in joins:
                    if join_model.__name__.lower() == relationship_name.lower():
                        related_model = join_model
                        break

                if related_model is not None:
                    conditions.append(getattr(related_model, attribute_name) == value)
            else:
                conditions.append(getattr(cls, key) == value)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        if order_by:
            stmt = stmt.order_by(order_by)
        
        if skip:
            stmt = stmt.offset(skip)

        if limit:
            stmt = stmt.limit(limit)

        return stmt
    
        

    @classmethod
    async def build_handler(cls, joins=None, order_by=None, skip: int = 0, limit: int = 20, **kwargs) -> Self:
        cached_query = await cls._build_query(joins, skip=skip, limit=limit, **kwargs)
        if order_by != None and cached_query != None:
            cached_query = cls._apply_ordering(cached_query, order_by)
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
    
        elif result.rowcount == 0:
            return None
        
        else:
            return result.rowcount
    


    @classmethod
    async def aggregate(cls, db_session: AsyncSession, field: str, agg_func: str = "sum", joins=None, **kwargs) -> Union[int, float, None]:
        if agg_func.lower() == "sum":
            aggregation = func.sum(getattr(cls, field))
        else:
            raise ValueError(f"Unsupported aggregation function '{agg_func}'")

        stmt = await cls.build_handler(joins=joins, **kwargs)
        stmt = stmt.select_from(cls).with_only_columns(aggregation)
        result = await db_session.execute(stmt)
        return result.scalar()



    @classmethod
    async def icontains(cls, db_session: AsyncSession, fields: list, value: str, joins=None, **kwargs) -> Union[Type[Any], Type["QueryMixin"]]:
        stmt = await cls.build_handler(joins=joins, **kwargs)
        
        conditions = [func.lower(getattr(cls, field)).contains(func.lower(value)) for field in fields]
        stmt = stmt.where(or_(*conditions))

        result = await db_session.execute(stmt)
        instances = result.scalars().all()
        return instances