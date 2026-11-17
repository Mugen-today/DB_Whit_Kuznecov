// Read-only queries adapted to current schema.
const AS_OF=new Date("2026-11-10T00:00:00Z");
// 1 Выборка первых 10 пациентов
db.Patient.find().limit(10);

// 2 Все записи справочника Gender
db.Gender.find();

// 3 Все записи справочника Social_group
db.Social_group.find();

// 4 Все записи справочника Severity
db.Severity.find();

// 5 Все записи справочника Influence
db.Influence.find();

// 6 Все записи справочника Reception
db.Reception.find();

// 7 Первые 10 регионов
db.Region.find().limit(10);

// 8 Количество документов в Pdtient
db.Patient.countDocuments({});

// 9 Количество документов в Instances
db.Instances.countDocuments({});

// 10 Количество документов в Therapy
db.Therapy.countDocuments({});

// 11 Пациенты старше 60 лет
db.Patient.find({ age: { $gt: 60 } });

// 12 Пациенты 18–40 лет включительно
db.Patient.find({ age: { $gte: 18, $lte: 40 } });

// 13 Пациенты с заполненным полем passport
db.Patient.find({ passport: { $ne: null } });

// 14 Пациенты, зарегистрированные с 2024-01-01
db.Patient.find({ reg_date: { $gte: new Date("2024-01-01") } });

// 15 Случаи лечения с госпитализацией
db.Therapy.find({ hospitalization: true });

// 16 Случаи лечения с рецидивом
db.Therapy.find({ relapse: true });

// 17 Терапия с диагнозом «ОРВИ» в массиве diagnosis
db.Therapy.find({ diagnosis: "ОРВИ" });

// 18 Случаи Instances за последние 30 дней
db.Instances.find({ date: { $gte: new Date(AS_OF.getTime() - 30 * 24 * 60 * 60 * 1000) } });

// 19 Instances с заполненным полем Other
db.Instances.find({ Other: { $exists: true, $nin: [null, ""] } });

// 20 Терапия с непустым side_effect
db.Therapy.find({ "result.side effect": { $exists: true, $nin: [null, ""] } });

// 21 Пациенты с указанной вакциной
db.Patient.find({ "medical_record.vaccine": { $exists: true, $nin: [null, ""] } });

// 22 Пациенты с хроническим заболеванием
db.Patient.find({ "medical_record.chronic_diseases": { $exists: true, $nin: [null, ""] } });

// 23 Пациенты с расшифрованным полом (JOIN Gender)
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "gender_info" } }, { $unwind: "$gender_info" }]);

// 24 Пациенты с расшифрованной социальной группой
db.Patient.aggregate([{ $lookup: { from: "Social_group", localField: "social_group", foreignField: "_id", as: "social_info" } }, { $unwind: "$social_info" }]);

// 25 Количество пациентов по каждому типу пола
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "g" } }, { $unwind: "$g" }, { $group: { _id: "$g.type", count: { $sum: 1 } } }]);

// 26 Количество пациентов по социальным группам
db.Patient.aggregate([{ $lookup: { from: "Social_group", localField: "social_group", foreignField: "_id", as: "s" } }, { $unwind: "$s" }, { $group: { _id: "$s.type", count: { $sum: 1 } } }]);

// 27 Список степеней тяжести
db.Severity.distinct("degree");

// 28 Список влияющих факторов
db.Influence.distinct("name");

// 29 Список типов приёма
db.Reception.distinct("type");

// 30 Мужчины-пациенты (пол «мужской»)
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "g" } }, { $unwind: "$g" }, { $match: { "g.type": "мужской" } }]);

// 31 Пациенты социальной группы «работающие»
db.Patient.aggregate([{ $lookup: { from: "Social_group", localField: "social_group", foreignField: "_id", as: "s" } }, { $unwind: "$s" }, { $match: { "s.type": "работающие" } }]);

// 32 Количество случаев лечения по степени тяжести
db.Therapy.aggregate([{ $lookup: { from: "Severity", localField: "severity", foreignField: "_id", as: "sv" } }, { $unwind: "$sv" }, { $group: { _id: "$sv.degree", count: { $sum: 1 } } }]);

// 33 10 самых пожилых пациентов
db.Patient.find().sort({ age: -1 }).limit(10);

// 34 Пациенты без указанного пола (ссылка пустая)
db.Patient.find({ gender: { $in: [null] } });

// 35 Минимальная и максимальная дата регистрации
db.Patient.aggregate([{ $group: { _id: null, min_date: { $min: "$reg_date" }, max_date: { $max: "$reg_date" } } }]);

// 36 Проверка структуры medical_record (есть ли оба поля)
db.Patient.find({ $or: [ { medical_record: { $exists: false } }, { "medical_record.chronic_diseases": { $exists: false } }, { "medical_record.vaccine": { $exists: false } } ] });

// 37 Значения пола, не найденные в справочнике Gender
db.Patient.aggregate([{$lookup:{from:"Gender",localField:"gender",foreignField:"_id",as:"g"}},{$match:{g:{$size:0}}},{$group:{_id:"$gender"}}]);

// 38 Пациенты по комбинации пол + социальная группа
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "g" } }, { $unwind: "$g" }, { $lookup: { from: "Social_group", localField: "social_group", foreignField: "_id", as: "s" } }, { $unwind: "$s" }, { $group: { _id: { gender: "$g.type", social: "$s.type" }, count: { $sum: 1 } } }]);

// 39 Регионы со связанными муниципалитетами
db.Region.aggregate([{ $lookup: { from: "Municipality", localField: "municipality", foreignField: "_id", as: "m" } }, { $unwind: "$m" }]);

// 40 Муниципалитеты с населенными пунктами
db.Municipality.aggregate([{ $lookup: { from: "Settlement", localField: "settlement", foreignField: "_id", as: "s" } }, { $unwind: "$s" }]);

// 41 Населенные пункты с улицами
db.Settlement.aggregate([{ $lookup: { from: "Street", localField: "street", foreignField: "_id", as: "st" } }, { $unwind: "$st" }]);

// 42 Улицы с домами
db.Street.aggregate([{ $lookup: { from: "Building", localField: "building", foreignField: "_id", as: "b" } }, { $unwind: "$b" }]);

// 43 Дома с помещениями
db.Building.aggregate([{ $lookup: { from: "Placement", localField: "placement", foreignField: "_id", as: "pl" } }, { $unwind: "$pl" }]);

// 44 Полная адресная цепочка: регион → помещение
db.Region.aggregate([
  { $lookup: { from: "Municipality", localField: "municipality", foreignField: "_id", as: "m" } },
  { $unwind: "$m" },
  { $lookup: { from: "Settlement", localField: "m.settlement", foreignField: "_id", as: "s" } },
  { $unwind: "$s" },
  { $lookup: { from: "Street", localField: "s.street", foreignField: "_id", as: "st" } },
  { $unwind: "$st" },
  { $lookup: { from: "Building", localField: "st.building", foreignField: "_id", as: "b" } },
  { $unwind: "$b" },
  { $lookup: { from: "Placement", localField: "b.placement", foreignField: "_id", as: "pl" } },
  { $unwind: "$pl" }
]);

// 45 Геоданные с валидной долготой (РФ)
db.Geodata.find({Longitude:{$gte:19,$lte:180}});

// 46 Геоданные с валидной широтой (РФ)
db.Geodata.find({ Latitude: { $gte: 41, $lte: 82 } });

// 47 Геоданные с пропущенными координатами
db.Geodata.find({ $or: [ { Longitude: { $in: [null] } }, { Latitude: { $in: [null] } } ] });

// 48 Статистика высоты: min, max, среднее
db.Geodata.aggregate([{ $group: { _id: null, min: { $min: "$Elevation" }, max: { $max: "$Elevation" }, avg: { $avg: "$Elevation" } } }]);

// 49 Локации без геоданных
db.Location.find({ "address.geodata": { $in: [null] } });

// 50 Локации без указанного региона
db.Location.find({ "address.region": { $in: [null] } });

// 51 Очаги с локацией
db.Foci.aggregate([{ $lookup: { from: "Location", localField: "location", foreignField: "_id", as: "l" } }, { $unwind: "$l" }]);

// 52 Локации с полностью пустым адресом
db.Location.find({ $or: [ { address: { $exists: false } }, { address: {} } ] });

// 53 Количество помещений в базе
db.Placement.countDocuments({});

// 54 Дубликаты геоточек (одинаковые координаты)
db.Geodata.aggregate([{ $group: { _id: { lon: "$Longitude", lat: "$Latitude" }, n: { $sum: 1 } } }, { $match: { n: { $gt: 1 } } }]);

// 55 Количество случаев по каждому очагу
db.Foci.aggregate([{$lookup:{from:"Instances",localField:"id_instance",foreignField:"instance",as:"i"}},{$project:{_id:1,count:{$size:"$i"}}}]);

// 56 Очаги без зарегистрированных случаев
db.Foci.aggregate([{ $lookup: { from: "Instances", localField: "id_instance", foreignField: "instance", as: "i" } }, { $match: { i: { $size: 0 } } }]);

// 57 Случаи без привязки к очагу
db.Instances.aggregate([{$lookup:{from:"Foci",localField:"instance",foreignField:"id_instance",as:"f"}},{$match:{f:{$size:0}}}]);

// 58 Дубликаты id_instance
db.Instances.aggregate([{ $group: { _id: "$instance", n: { $sum: 1 } } }, { $match: { n: { $gt: 1 } } }]);

// 59 Случаи по дням
db.Instances.aggregate([{ $group: { _id: { $dateToString: { format: "%Y-%m-%d", date: "$date" } }, count: { $sum: 1 } } }, { $sort: { _id: 1 } }]);

// 60 Распределение случаев по полю Other
db.Instances.aggregate([{ $group: { _id: "$Other", count: { $sum: 1 } } }]);

// 61 Случаи с типом приёма
db.Instances.aggregate([{ $lookup: { from: "Reception", localField: "reception", foreignField: "_id", as: "r" } }, { $unwind: "$r" }]);

// 62 Пациенты с более чем одним случаем заболевания
db.Instances.aggregate([{ $group: { _id: "$patient", n: { $sum: 1 } } }, { $match: { n: { $gt: 1 } } }]);

// 63 Случаи с данными пациента
db.Instances.aggregate([{ $lookup: { from: "Patient", localField: "patient", foreignField: "_id", as: "p" } }, { $unwind: "$p" }]);

// 64 Самая ранняя и самая поздняя дата случая
db.Instances.aggregate([{ $group: { _id: null, min_date: { $min: "$date" }, max_date: { $max: "$date" } } }]);

// 65 Случаи без привязки к типу приёма
db.Instances.find({ reception: { $in: [null] } });

// 66 Случаи без привязки к пациенту
db.Instances.find({ patient: { $in: [null] } });

// 67 Количество очагов по региону
db.Foci.aggregate([{ $lookup: { from: "Location", localField: "location", foreignField: "_id", as: "l" } }, { $unwind: "$l" }, { $lookup: { from: "Region", localField: "l.address.region", foreignField: "_id", as: "r" } }, { $unwind: "$r" }, { $group: { _id: "$r.name", count: { $sum: 1 } } }]);

// 68 Случаи с данными о терапии
db.Instances.aggregate([{ $lookup: { from: "Therapy", localField: "therapy", foreignField: "_id", as: "t" } }, { $unwind: "$t" }]);

// 69 Количество курсов терапии по степени тяжести
db.Therapy.aggregate([{ $group: { _id: "$severity", count: { $sum: 1 } } }]);

// 70 Количество курсов по влияющему фактору
db.Therapy.aggregate([{ $group: { _id: "$influence", count: { $sum: 1 } } }]);

// 71 Терапия с рецидивом и госпитализацией одновременно
db.Therapy.find({ relapse: true, hospitalization: true });

// 72 Средняя длительность терапии в днях (от date_start до сегодня)
db.Therapy.aggregate([{ $project: { days: { $divide: [ { $subtract: [ AS_OF, "$date_start" ] }, 86400000 ] } } }, { $group: { _id: null, avg_days: { $avg: "$days" } } }]);

// 73 Терапия без указания степени тяжести
db.Therapy.find({ severity: { $in: [null] } });

// 74 Терапия без привязки к пациенту
db.Therapy.find({ patient: { $in: [null] } });

// 75 Количество курсов с исходом «не спасён»
db.Therapy.countDocuments({ "result.Saved": false });

// 76 Количество курсов с исходом «выздоровел»
db.Therapy.countDocuments({ "result.recovery": true });

// 77 Курсы с зафиксированными побочными эффектами
db.Therapy.find({ "result.side effect": { $exists: true, $nin: [null, ""] } });

// 78 Распределение курсов по количеству диагнозов в массиве
db.Therapy.aggregate([{ $project: { n: { $size: { $ifNull: [ "$diagnosis", [] ] } } } }, { $group: { _id: "$n", count: { $sum: 1 } } }, { $sort: { _id: 1 } }]);

// 79 Средний возраст по полу
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "g" } }, { $unwind: "$g" }, { $group: { _id: "$g.type", avg_age: { $avg: "$age" } } }]);

// 80 Случаи заболеваний по месяцам
db.Instances.aggregate([{ $group: { _id: { $dateToString: { format: "%Y-%m", date: "$date" } }, count: { $sum: 1 } } }, { $sort: { _id: 1 } }]);

// 81 Количество случаев по регионам (полная цепочка связей)
db.Instances.aggregate([
  { $lookup: { from: "Foci", localField: "instance", foreignField: "id_instance", as: "f" } },
  { $unwind: "$f" },
  { $lookup: { from: "Location", localField: "f.location", foreignField: "_id", as: "l" } },
  { $unwind: "$l" },
  { $lookup: { from: "Region", localField: "l.address.region", foreignField: "_id", as: "r" } },
  { $unwind: "$r" },
  { $group: { _id: "$r.name", count: { $sum: 1 } } }
]);

// 82 Топ-10 регионов по числу случаев
db.Instances.aggregate([
  { $lookup: { from: "Foci", localField: "instance", foreignField: "id_instance", as: "f" } },
  { $unwind: "$f" },
  { $lookup: { from: "Location", localField: "f.location", foreignField: "_id", as: "l" } },
  { $unwind: "$l" },
  { $lookup: { from: "Region", localField: "l.address.region", foreignField: "_id", as: "r" } },
  { $unwind: "$r" },
  { $group: { _id: "$r.name", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
]);

// 83 Средний возраст госпитализированных по социальным группам
db.Instances.aggregate([
  { $lookup: { from: "Therapy", localField: "therapy", foreignField: "_id", as: "t" } },
  { $unwind: "$t" },
  { $match: { "t.hospitalization": true } },
  { $lookup: { from: "Patient", localField: "patient", foreignField: "_id", as: "p" } },
  { $unwind: "$p" },
  { $lookup: { from: "Social_group", localField: "p.social_group", foreignField: "_id", as: "s" } },
  { $unwind: "$s" },
  { $group: { _id: "$s.type", avg_age: { $avg: "$p.age" } } }
]);

// 84 Количество случаев по типам приёма
db.Instances.aggregate([{ $lookup: { from: "Reception", localField: "reception", foreignField: "_id", as: "r" } }, { $unwind: "$r" }, { $group: { _id: "$r.type", count: { $sum: 1 } } }]);

// 85 Доля рецидивов по степеням тяжести
db.Therapy.aggregate([{ $lookup: { from: "Severity", localField: "severity", foreignField: "_id", as: "sv" } }, { $unwind: "$sv" }, { $group: { _id: "$sv.degree", relapse_rate: { $avg: { $cond: [ "$relapse", 1, 0 ] } } } }]);

// 86 Распределение пациентов по возрастным группам
db.Patient.aggregate([{ $bucket: { groupBy: "$age", boundaries: [0, 18, 40, 60, 200], default: "без возраста", output: { count: { $sum: 1 } } } }]);

// 87 Количество случаев по полам пациентов
db.Instances.aggregate([{ $lookup: { from: "Patient", localField: "patient", foreignField: "_id", as: "p" } }, { $unwind: "$p" }, { $lookup: { from: "Gender", localField: "p.gender", foreignField: "_id", as: "g" } }, { $unwind: "$g" }, { $group: { _id: "$g.type", count: { $sum: 1 } } }]);

// 88 Топ-10 хронических заболеваний среди пациентов
db.Patient.aggregate([{ $group: { _id: "$medical_record.chronic_diseases", count: { $sum: 1 } } }, { $sort: { count: -1 } }, { $limit: 10 }]);

// 89 Среднее количество случаев на один очаг
db.Foci.aggregate([{$lookup:{from:"Instances",localField:"id_instance",foreignField:"instance",as:"i"}},{$group:{_id:null,avg_per_focus:{$avg:{$size:"$i"}}}}]);

// 90 Новые пациенты по месяцам регистрации
db.Patient.aggregate([{ $group: { _id: { $dateToString: { format: "%Y-%m", date: "$reg_date" } }, count: { $sum: 1 } } }, { $sort: { _id: 1 } }]);

// 91 Instances со «висячей» ссылкой на пациента
db.Instances.aggregate([{ $lookup: { from: "Patient", localField: "patient", foreignField: "_id", as: "p" } }, { $match: { p: { $size: 0 } } }, { $count: "orphans" }]);

// 92 Instances со «висячей» ссылкой на терапию
db.Instances.aggregate([{ $lookup: { from: "Therapy", localField: "therapy", foreignField: "_id", as: "t" } }, { $match: { t: { $size: 0 } } }, { $count: "orphans" }]);

// 93 Instances со «висячей» ссылкой на тип приёма
db.Instances.aggregate([{ $lookup: { from: "Reception", localField: "reception", foreignField: "_id", as: "r" } }, { $match: { r: { $size: 0 } } }, { $count: "orphans" }]);

// 94 Therapy со «висячей» ссылкой на пациента
db.Therapy.aggregate([{ $lookup: { from: "Patient", localField: "patient", foreignField: "_id", as: "p" } }, { $match: { p: { $size: 0 } } }, { $count: "orphans" }]);

// 95 Pdtient со «висячей» ссылкой на пол
db.Patient.aggregate([{ $lookup: { from: "Gender", localField: "gender", foreignField: "_id", as: "g" } }, { $match: { g: { $size: 0 } } }, { $count: "orphans" }]);

// 96 Pdtient со «висячей» ссылкой на социальную группу
db.Patient.aggregate([{ $lookup: { from: "Social_group", localField: "social_group", foreignField: "_id", as: "s" } }, { $match: { s: { $size: 0 } } }, { $count: "orphans" }]);

// 97 Foci со «висячей» ссылкой на локацию
db.Foci.aggregate([{ $lookup: { from: "Location", localField: "location", foreignField: "_id", as: "l" } }, { $match: { l: { $size: 0 } } }, { $count: "orphans" }]);

// 98 Локации со «висячей» ссылкой на геоданные
db.Location.aggregate([{ $lookup: { from: "Geodata", localField: "address.geodata", foreignField: "_id", as: "g" } }, { $match: { g: { $size: 0 } } }, { $count: "orphans" }]);

// 99 Therapy со «висячей» ссылкой на степень тяжести
db.Therapy.aggregate([{ $lookup: { from: "Severity", localField: "severity", foreignField: "_id", as: "sv" } }, { $match: { sv: { $size: 0 } } }, { $count: "orphans" }]);

// 100 Instances со «висячей» ссылкой на очаг
db.Instances.aggregate([{$lookup:{from:"Foci",localField:"instance",foreignField:"id_instance",as:"f"}},{$match:{f:{$size:0}}},{$count:"orphans"}]);