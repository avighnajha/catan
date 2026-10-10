import uuid

from fastapi.testclient import TestClient

from tests.test_builtin_rooms import account


def test_owner_can_edit_metadata_remove_library_entry_and_keep_original_code(monkeypatch):
    from src.platform import server
    from src.platform.bot_registry import BotRegistry
    monkeypatch.setattr(server,'AUTH_REQUIRED',True)
    client=TestClient(server.app)
    owner,stranger=account(client),account(client)
    name='Editable'+uuid.uuid4().hex[:8]
    code='from src.player import Player\nclass P(Player):\n def choose_action(self,view,options): return options[0]\n'
    response=client.post('/bots/upload',headers=owner,json={'bot_name':name,'bot_version':'v1','bot_code':code})
    assert response.status_code==200,response.text
    bid=response.json()['bot_id']
    assert client.get('/bots/'+bid,headers=owner).json()['bot_code']==code
    for headers in ({},stranger):
        assert client.patch('/bots/'+bid,headers=headers,json={'bot_name':'Stolen'}).status_code in (401,403)
        assert client.delete('/bots/'+bid,headers=headers).status_code in (401,403)
        assert client.get('/bots/'+bid,headers=headers).status_code in (401,403)
    edited=client.patch('/bots/'+bid,headers=owner,json={'bot_name':name+' renamed','description':'Updated description'})
    assert edited.status_code==200 and edited.json()['description']=='Updated description'
    assert server.bot_registry.get_bot(bid).bot_code==code
    assert client.patch('/bots/'+bid,headers=owner,json={'bot_name':name,'bot_code':'replacement'}).status_code==422
    assert client.delete('/bots/'+bid,headers=owner).status_code==200
    assert bid not in [b['bot_id'] for b in client.get('/bots',headers=owner).json()['bots']]
    assert client.get('/bots/'+bid,headers=owner).status_code==404
    assert client.post('/bots/test',headers=owner,json={'bot_id':bid,'difficulty':'easy'}).status_code==404
    assert client.get('/account/stats',headers=owner).json()['bots']==0
    # Retained immutable code survives reopening the registry for queued workers.
    reopened=BotRegistry(database_url=server.DATABASE_URL)
    assert reopened.get_bot(bid).bot_code==code
    assert bid not in [b['bot_id'] for b in reopened.list_bots()]
    response=client.post('/bots/upload',headers=owner,json={'bot_name':name,'bot_version':'v1','bot_code':code})
    assert response.status_code==409
    assert client.post('/bots/upload',headers=owner,json={'bot_name':name,'bot_version':'v2','bot_code':code}).status_code==200


def test_optional_auth_still_blocks_anonymous_changes_to_owned_bots(monkeypatch):
    from src.platform import server
    client=TestClient(server.app)
    owner=account(client)
    user_id=client.get('/auth/me',headers=owner).json()['user']['user_id']
    bot=server.bot_registry.register('Owned'+uuid.uuid4().hex,'v1',owner_id=user_id)
    monkeypatch.setattr(server,'AUTH_REQUIRED',False)
    assert client.patch('/bots/'+bot.bot_id,json={'bot_name':'Wrong'}).status_code==403
    assert client.delete('/bots/'+bot.bot_id).status_code==403
    assert 'bot_code' not in client.get('/bots/'+bot.bot_id).json()
