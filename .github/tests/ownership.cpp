#include "4DPlugin-codec.h"
#include "4DPlugin-JSON.h"
#include "ARRAY_TEXT.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <set>

namespace {
std::set<PA_Unichar*> strings;
std::map<PA_Handle, size_t> handles;
std::set<PA_Picture> pictures;
bool nullEmpty = false;
bool failGetter = false;
size_t clears = 0;
const PA_Unichar empty[] = {0};
typedef std::basic_string<PA_Unichar> Text;

struct Ref {
    size_t owners = 1;
    std::map<Text, PA_Variable> properties;
};
std::set<Ref*> refs;

// SDK structures are packed to two bytes; STL reference arguments need copies.
template <typename T> T aligned(T value) { return value; }

Text text(const PA_Unistring& value) {
    assert(value.fLength >= 0);
    if (!value.fString) {
        assert(value.fLength == 0);
        return Text();
    }
    assert(strings.count(aligned(value.fString)));
    assert(value.fString[value.fLength] == 0);
    return Text(value.fString, value.fLength);
}

PA_Unistring makeString(const PA_Unichar* value) {
    PA_Unistring result = {};
    if (!value) value = empty;
    while (value[result.fLength]) ++result.fLength;
    if (result.fLength || !nullEmpty) {
        result.fString = new PA_Unichar[result.fLength + 1];
        std::memcpy(result.fString, value, (result.fLength + 1) * sizeof(PA_Unichar));
        strings.insert(aligned(result.fString));
    }
    return result;
}

void freeString(PA_Unistring& value) {
    if (value.fString) {
        assert(strings.erase(aligned(value.fString)) == 1);
        delete[] value.fString;
    }
    value = {};
}

PA_Handle newHandle(size_t size) {
    PA_Handle h = new char*;
    *h = new char[size ? size : 1]();
    handles[h] = size;
    return h;
}

void freeHandle(PA_Handle h) {
    if (!h) return;
    assert(handles.erase(h) == 1);
    delete[] *h;
    delete h;
}

Ref* newRef() {
    Ref* ref = new Ref;
    refs.insert(ref);
    return ref;
}

void clear(PA_Variable&);
void release(void* ptr) {
    if (!ptr) return;
    Ref* ref = static_cast<Ref*>(ptr);
    assert(refs.count(ref));
    assert(ref->owners);
    if (--ref->owners == 0) {
        for (auto& item : ref->properties) clear(item.second);
        refs.erase(ref);
        delete ref;
    }
}

PA_Variable copy(PA_Variable value) {
    if (value.fType == eVK_Unistring) {
        Text contents = text(value.uValue.fString);
        value.uValue.fString = makeString(contents.c_str());
    } else if (value.fType == eVK_Object || value.fType == eVK_Collection) {
        Ref* ref = static_cast<Ref*>(value.fType == eVK_Object
            ? value.uValue.fObject : value.uValue.fCollection);
        if (ref) {
            assert(refs.count(ref));
            ++ref->owners;
        }
    } else if (value.fType == eVK_Picture && value.uValue.fPicture) {
        assert(pictures.count(aligned(value.uValue.fPicture)));
        value.uValue.fPicture = new char;
        pictures.insert(aligned(value.uValue.fPicture));
    }
    return value;
}

void clear(PA_Variable& value) {
    ++clears;
    switch (value.fType) {
        case eVK_Unistring: freeString(value.uValue.fString); break;
        case eVK_Object: release(value.uValue.fObject); break;
        case eVK_Collection: release(value.uValue.fCollection); break;
        case eVK_Picture:
            if (value.uValue.fPicture) {
                assert(pictures.erase(aligned(value.uValue.fPicture)) == 1);
                delete static_cast<char*>(value.uValue.fPicture);
            }
            break;
        case eVK_ArrayUnicode: {
            PA_Unistring* data = reinterpret_cast<PA_Unistring*>(*value.uValue.fArray.fData);
            for (int i = 0; i <= value.uValue.fArray.fNbElements; ++i) freeString(data[i]);
            freeHandle(value.uValue.fArray.fData);
            break;
        }
        case eVK_Undefined: case eVK_Boolean: case eVK_Real: case eVK_Longint: break;
        default: assert(!"unexpected clear kind");
    }
    value = {};
    value.fType = eVK_Undefined;
}

void engine(short selector, EngineBlock* eb) {
    eb->fError = eER_NoErr;
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            break;
        case EX_DISPOSE_UNISTRING: freeString(eb->fUniString1); break;
        case EX_SET_UNISTRING: {
            Text contents(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            freeString(eb->fUniString1);
            eb->fUniString1 = makeString(contents.c_str());
            break;
        }
        case EX_CLEAR_VARIABLE: clear(*static_cast<PA_Variable*>(eb->fPtr1)); break;
        case EX_VARIABLE_TO_STRING: {
            PA_Variable* variable = reinterpret_cast<PA_Variable*>(eb->fHandle);
            assert(variable->fType == eVK_Unistring);
            text(variable->uValue.fString);
            eb->fUniString1 = variable->uValue.fString;
            break;
        }
        case EX_HANDLE_MANAGER: {
            switch (eb->fParam1) {
                case 1: eb->fHandle = newHandle(eb->fParam2); break;
                case 2: freeHandle(eb->fHandle); break;
                case 3: {
                    size_t old = handles.at(aligned(eb->fHandle)), size = eb->fParam2;
                    char* data = new char[size ? size : 1]();
                    std::memcpy(data, *eb->fHandle, std::min(old, size));
                    delete[] *eb->fHandle;
                    *eb->fHandle = data;
                    handles[aligned(eb->fHandle)] = size;
                    break;
                }
                case 4: eb->fParam2 = handles.at(aligned(eb->fHandle)); break;
                case 5: eb->fParam3 = reinterpret_cast<sLONG_PTR>(*eb->fHandle); break;
                case 6: break;
                default: assert(!"unexpected handle operation");
            }
            break;
        }
        case EX_CREATE_PICTURE:
            eb->fPicture = new char;
            pictures.insert(aligned(eb->fPicture));
            break;
        case EX_GET_OBJ_VALUE: {
            if (failGetter) {
                // Failed outputs are deliberately hostile, not owning values.
                std::memset(eb->fPtr2, 0xa5, sizeof(PA_Variable));
                eb->fError = eER_IncompatibleTypes;
                break;
            }
            Ref* ref = static_cast<Ref*>(eb->fPtr1);
            assert(refs.count(ref));
            *static_cast<PA_Variable*>(eb->fPtr2) = copy(ref->properties.at(text(eb->fUniString1)));
            break;
        }
        case EX_SET_OBJ_VALUE: {
            Ref* ref = static_cast<Ref*>(eb->fPtr1);
            assert(refs.count(ref));
            Text key = text(eb->fUniString1);
            auto old = ref->properties.find(key);
            if (old != ref->properties.end()) clear(old->second);
            ref->properties[key] = copy(*static_cast<PA_Variable*>(eb->fPtr2));
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            PA_Variable** args = static_cast<PA_Variable**>(eb->fPtr1);
            PA_Variable* result = static_cast<PA_Variable*>(eb->fPtr2);
            if (eb->fParam1 == 1231) {
                Ref* ref = static_cast<Ref*>(args[0]->uValue.fObject);
                assert(refs.count(ref));
                PA_SetBooleanVariable(result, ref->properties.count(text(args[1]->uValue.fString)) != 0);
            } else if (eb->fParam1 == 1225) {
                Ref* source = static_cast<Ref*>(args[0]->uValue.fObject);
                assert(refs.count(source));
                Ref* duplicate = newRef();
                for (auto& item : source->properties) duplicate->properties[item.first] = copy(item.second);
                PA_SetObjectVariable(result, duplicate);
            } else if (eb->fParam1 == 1217) {
                Ref* ref = static_cast<Ref*>(args[0]->uValue.fObject);
                assert(refs.count(ref));
                *result = copy(ref->properties.at(Text(1, 's')));
            } else {
                assert(!"unexpected command");
            }
            break;
        }
        default:
            std::cerr << "Unhandled engine selector " << selector << "\n";
            std::abort();
    }
}

void balanced(const char* label) {
    if (!strings.empty() || !handles.empty() || !refs.empty() || !pictures.empty()) {
        std::cerr << label << ": leaked strings=" << strings.size()
                  << " handles=" << handles.size() << " refs=" << refs.size()
                  << " pictures=" << pictures.size() << "\n";
        std::exit(1);
    }
}

const PA_Unichar ascii[] = {'A', 'S', 'C', 'I', 'I', 0};
const PA_Unichar bmp[] = {0x65e5, 0x672c, 0};
const PA_Unichar supplementary[] = {'x', 0xd83d, 0xde00, 0};
const PA_Unichar* fixtures[] = {ascii, bmp, supplementary, empty};
const std::string fixtureBytes[] = {"ASCII", "\xe6\x97\xa5\xe6\x9c\xac",
                                    "x\xf0\x9f\x98\x80", ""};

std::string utf8(const PA_Unichar* value) {
    C_TEXT converted;
    converted.setUTF16String(value, static_cast<uint32_t>(Text(value).size()));
    CUTF8String result;
    converted.copyUTF8String(&result);
    return std::string(result.begin(), result.end());
}

void setters() {
    const wchar_t* wide[] = {L"ASCII", L"\u65e5\u672c", L"x\U0001f600", L""};
    for (bool nulls : {false, true}) {
        nullEmpty = nulls;
        for (size_t i = 0; i < 4; ++i) {
            Ref* obj = newRef();
            Text source(fixtures[i]);
            std::string bytes = utf8(fixtures[i]);
            assert(bytes == fixtureBytes[i]);
            for (int repeat = 0; repeat < 2; ++repeat) {
                ob_set_s(obj, "s", bytes.c_str());
                ob_set_s(obj, L"w", bytes.c_str());
                ob_set_a(obj, L"a", wide[i]);
                ob_set_a(obj, L"u", &source);
            }
            for (PA_Unichar key : {'s', 'w', 'a', 'u'})
                assert(text(obj->properties.at(Text(1, key)).uValue.fString) == source);
            PA_DisposeObject(obj);
            balanced("setter initial-empty overwrite");
        }
    }
}

void picture() {
    Ref* obj = newRef();
    PA_Picture value = PA_CreatePicture(nullptr, 0);
    ob_set_p(obj, L"p", value);
    assert(pictures.count(aligned(obj->properties.at(Text(1, 'p')).uValue.fPicture)));
    PA_DisposeObject(obj);
    balanced("picture initial-empty overwrite");
}

void getters() {
    for (bool nulls : {false, true}) {
        nullEmpty = nulls;
        for (const PA_Unichar* fixture : fixtures) {
            Ref* obj = newRef();
            PA_Variable v = {};
            v.fType = eVK_Unistring;
            v.uValue.fString = makeString(fixture);
            obj->properties[Text(1, 's')] = v;
            PA_SetBooleanVariable(&v, true);
            obj->properties[Text(1, 'b')] = v;
            PA_SetRealVariable(&v, 3.25);
            obj->properties[Text(1, 'n')] = v;
            Ref* collection = newRef();
            PA_SetCollectionVariable(&v, collection);
            obj->properties[Text(1, 'c')] = v;
            const size_t initial = strings.size();
            CUTF8String output;
            assert(ob_get_a(obj, L"s", &output));
            assert(std::string(output.begin(), output.end()) == utf8(fixture));
            assert(strings.size() == initial);
            size_t scalarClears = clears;
            assert(ob_get_b(obj, L"b"));
            assert(ob_get_n(obj, L"n") == 3.25);
            assert(clears == scalarClears + 2);
            // Mismatches must release successful owning results, regardless of type.
            ob_get_b(obj, L"s");
            ob_get_n(obj, L"s");
            assert(!ob_get_c(obj, L"s"));
            ob_get_a(obj, L"c", &output);
            ob_get_b(obj, L"c");
            ob_get_n(obj, L"c");
            assert(collection->owners == 1);
            assert(strings.size() == initial);
            PA_CollectionRef handoff = ob_get_c(obj, L"c");
            assert(handoff == collection && collection->owners == 2);
            CUTF8String json;
            ob_stringify(obj, &json);
            assert(std::string(json.begin(), json.end()) == utf8(fixture));
            failGetter = true;
            size_t before = clears;
            assert(!ob_get_a(obj, L"s", &output));
            assert(!ob_get_b(obj, L"s"));
            assert(ob_get_n(obj, L"s") == 0);
            assert(!ob_get_c(obj, L"s"));
            assert(clears == before);
            failGetter = false;
            PA_DisposeObject(obj);
            assert(refs.count(static_cast<Ref*>(handoff)));
            assert(collection->owners == 1);
            PA_DisposeCollection(handoff);
            assert(!ob_get_b(nullptr, L"b"));
            balanced("owning property result");
        }
    }
}

void mismatchedGetter(const std::string& kind) {
    for (PA_VariableKind type : {eVK_Unistring, eVK_Object, eVK_Collection}) {
        Ref* obj = newRef();
        PA_Variable value = {};
        if (type == eVK_Unistring) {
            value.fType = eVK_Unistring;
            value.uValue.fString = makeString(supplementary);
        } else if (type == eVK_Object) {
            PA_SetObjectVariable(&value, newRef());
        } else {
            PA_SetCollectionVariable(&value, newRef());
        }
        obj->properties[Text(1, 's')] = value;
        if (kind == "boolean") assert(!ob_get_b(obj, L"s"));
        else if (kind == "number") assert(ob_get_n(obj, L"s") == 0);
        else {
            PA_CollectionRef result = ob_get_c(obj, L"s");
            if (type == eVK_Collection) {
                assert(result == value.uValue.fCollection);
                PA_DisposeCollection(result);
            } else assert(!result);
        }
        PA_DisposeObject(obj);
        balanced("mismatched owning getter result");
    }
}

void arrays() {
    for (bool nulls : {false, true}) {
        nullEmpty = nulls;
        PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
        PA_ResizeArray(&array, 4);
        for (int i = 0; i < 4; ++i) {
            PA_Unistring owned = PA_CreateUnistring(const_cast<PA_Unichar*>(fixtures[i]));
            PA_SetStringInArray(array, i, &owned);
            assert(PA_GetStringInArray(array, i).fString == owned.fString);
        }
        ARRAY_TEXT saved;
        BytePtr params[] = {reinterpret_cast<BytePtr>(&array)};
        saved.fromParamAtIndex(params, 1);
        for (int i = 0; i < 4; ++i) {
            PA_Unistring borrowed = PA_GetStringInArray(array, i);
            PA_Unistring independent = PA_CreateUnistring(borrowed.fString);
            PA_SetStringInArray(array, i, &independent);
            Text actual;
            saved.copyUTF16StringAtIndex(&actual, i);
            assert(actual == Text(fixtures[i]));
        }
        for (int i = 0; i < 32; ++i) {
            PA_Unistring churn = PA_CreateUnistring(const_cast<PA_Unichar*>(supplementary));
            PA_DisposeUnistring(&churn);
        }
        // A second output receives independently created owners, not source aliases.
        PA_Variable other = PA_CreateVariable(eVK_Undefined);
        BytePtr target[] = {reinterpret_cast<BytePtr>(&other)};
        saved.toParamAtIndex(target, 1);
        for (int i = 0; i < 4; ++i) {
            PA_Unistring a = PA_GetStringInArray(array, i);
            PA_Unistring b = PA_GetStringInArray(other, i);
            if (a.fString) assert(a.fString != b.fString);
        }
        PA_ResizeArray(&array, 0);
        PA_ClearVariable(&array);
        for (int i = 0; i < 4; ++i)
            assert(text(PA_GetStringInArray(other, i)) == Text(fixtures[i]));
        PA_Unistring retained = PA_CreateUnistring(const_cast<PA_Unichar*>(ascii));
        const size_t count = strings.size();
        PA_Variable wrong = PA_CreateVariable(eVK_Longint);
        PA_Variable noData = {};
        noData.fType = eVK_ArrayUnicode;
        PA_SetStringInArray(wrong, 0, &retained);
        PA_SetStringInArray(noData, 0, &retained);
        PA_SetStringInArray(other, -1, &retained);
        PA_SetStringInArray(other, 99, &retained);
        PA_SetStringInArray(other, 0, nullptr);
        assert(strings.size() == count && text(retained) == Text(ascii));
        PA_DisposeUnistring(&retained);
        PA_ClearVariable(&other);
        balanced("array transfers/rejections");
    }
}

void dispatcher() {
    const char* expected[] = {"QUJD", "QUJD", "QUJD", "IFBEG===",
                             "85146", "85146===", "414243", "414243"};
    for (int codec = 0; codec < 8; ++codec) {
        PA_Handle input = newHandle(3);
        std::memcpy(*input, "ABC", 3);
        PA_Unistring encoded = makeString(empty);
        PA_Unistring* result = &encoded;
        BytePtr args[] = {reinterpret_cast<BytePtr>(&input), reinterpret_cast<BytePtr>(&codec)};
        PluginBlock call = {};
        call.fParameters = args;
        call.fResult = &result;
        PluginMain(1, &call);
        assert(utf8(encoded.fString) == expected[codec]);
        PA_Handle decoded = nullptr;
        args[0] = reinterpret_cast<BytePtr>(&encoded);
        call.fResult = &decoded;
        PluginMain(2, &call);
        assert(handles.at(decoded) == 3 && std::memcmp(*decoded, "ABC", 3) == 0);
        freeHandle(decoded);
        freeString(encoded);
        freeHandle(input);
        balanced("actual scalar dispatcher");
    }
}
}

int main(int argc, char** argv) {
    assert(argc == 2);
    gCall4D = engine;
    std::string scenario(argv[1]);
    if (scenario == "setters") setters();
    else if (scenario == "picture") picture();
    else if (scenario == "getters") getters();
    else if (scenario == "boolean" || scenario == "number" || scenario == "collection")
        mismatchedGetter(scenario);
    else if (scenario == "arrays") arrays();
    else if (scenario == "dispatcher") dispatcher();
    else return 2;
    balanced("final");
    std::cout << scenario << ": exact content and all ownership balances passed\n";
}
