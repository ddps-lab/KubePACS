import pickle

az_map_dict = pickle.load(open('data/az_map_dict.pkl', 'rb'))
azdict = {}
for k, val in az_map_dict.items():
    azdict[k[1]]=val

def azchange(az):
    return azdict[az]

if __name__ == "__main__":    
    for i  in azdict.items():
        print(i)