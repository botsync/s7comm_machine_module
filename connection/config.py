import json

def add_machine_config(uid:str,machine_name:str,config:str):
    config = json.loads(config)
    config["machine_name"]=machine_name
  
    data = None
    with open('config.json','r+') as file:
        data = json.load(file)
    if data != None:
        data[uid] = config
        with open('config.json','w+') as out:
            json.dump(data,out)
    return True

def delete_machine_config(uid:str):
    with open('config.json','r+') as file:
        data = json.load(file)
    if data != None:
        value = data.get(uid)
        if value:
            del data[uid]
            with open('config.json','w+') as out:
                json.dump(data,out)
        return value
    return None

def get_machine_config(uid:str):
    with open('config.json','r+') as file:
        return json.load(file).get(uid,{})

def get_all_machines():
    with open('config.json','r+') as file:
        file = json.load(file)
        return file.items()