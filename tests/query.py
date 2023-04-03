import sys, os
current_dir = os.path.abspath('.')
sys.path.insert(0, current_dir)

from sqlalchemy.orm import declarative_base
from sqlalchemy import (
    select
)
from fastapi_integration.db import Engine
from fastapi_integration.models import AbstractBaseUser
from tests.start import MyConfig
import random, string, unittest


def get_random_info():
    username = ''.join(random.choices(string.ascii_lowercase, k=8))    
    domain = ''.join(random.choices(string.ascii_lowercase, k=8))    
    email = username + "@" + domain + ".com"
    icontain_email = username[:-3] + "@" + domain + ".com"
    return (username, email, icontain_email)


class TestQueryMixin(unittest.IsolatedAsyncioTestCase):


        
    async def asyncSetUp(self):
        async with db_engine.get_pg_db_with_async() as session:
            self.new_email = str(random_info[1]).join(random.choices(string.ascii_lowercase, k=2))
            new_username = str(random_info[2]).join(random.choices(string.ascii_lowercase, k=2))
            
            self.create_user = await User.create(email=random_info[1], username=random_info[0], password="testpassword", db_session=session)
            self.create_user_two = await User.create(email=self.new_email, username=new_username, password="testpassword", db_session=session)
            self.filter_icontain = await User.filter(email__icontains=random_info[2][:2], db_session=session)
            self.all_query = await User.all(db_session=session)
            self.startswith = await User.filter(username__startswith=random_info[1][:3], db_session=session)
            self.istartswith = await User.filter(username__istartswith=random_info[1][:3].upper(), db_session=session)
            self.delete = await User.delete(email=random_info[1], db_session=session)
            self.delete_icontians = await User.delete(email__icontains=random_info[2][:2], db_session=session)
            self.filter_gte = await User.filter(id__gte=1, db_session=session)
            self.filter_lte = await User.filter(id__lte=0, db_session=session)




    async def asyncTearDown(self):                     
        async with db_engine.get_pg_db_with_async() as session:  
            await User.delete(email=self.new_email, db_session=session)


        async with db_engine.engine.connect() as conn:
            await conn.close()
            await db_engine.engine.dispose()



    async def test_user_create_query(self):
        self.assertEqual(self.create_user.email, random_info[1])

    async def test_user_delete_query(self):
        self.assertEqual(self.delete, 1)

    async def test_user_all_query(self):
        self.assertGreater(len(self.all_query), 1)
    
    async def test_user_icontain_filter(self):
        self.assertEqual(len(self.filter_icontain), 2)
    
    async def test_user_icontain_delete(self):
        self.assertEqual(self.delete_icontians, 1)
    
    async def test_user_filter_gte(self):
        self.assertGreater(len(self.filter_gte), 0)
    
    async def test_user_filter_lte(self):
        self.assertEqual(len(self.filter_lte), 0)
    
    async def test_user_starts_with(self):
        self.assertEqual(len(self.startswith), 1)
    
    async def test_user_istarts_with(self):
        self.assertEqual(len(self.istartswith), 1)
    
    
    


if __name__ == "__main__":
    Base = declarative_base()
    class User(AbstractBaseUser, Base):
        __tablename__ = "users"


    random_info = get_random_info()
    db_engine = Engine(MyConfig())
    unittest.main()
