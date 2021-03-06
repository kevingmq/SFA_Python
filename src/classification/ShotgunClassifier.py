from src.timeseries.TimeSeries import *
import progressbar
from joblib import Parallel, delayed

class ShotgunClassifier():

    def __init__(self, d):
        self.NAME = d
        self.factor = 1.
        self.MAX_WINDOW_LENGTH = 250


    def eval(self, train, test, train_labels, test_labels):
        correctTraining = self.fit(train, train_labels)
        train_acc = correctTraining/len(train_labels)

        correctTesting, labels = self.predict(self.model, test, test_labels)
        test_acc = correctTesting/len(test_labels)

        return "Shotgun; "+str(round(train_acc,3))+"; "+str(round(test_acc,3)), labels


    def fit(self, train, train_labels):
        bestCorrectTraining = 0

        for normMean in [True, False]:
            model, correct = self.fitEnsemble(normMean, train, train_labels, self.factor)

            if correct > bestCorrectTraining:
                bestCorrectTraining = correct
                self.model = model[-1]
        return bestCorrectTraining


    def fitIndividual(self, NormMean, samples, labels, windows, i, bar):
        model = ShotgunModel(NormMean, windows[i], samples, labels)
        correct, pred_labels = self.predict(model, samples, labels)
        model.correct = correct
        bar.update(i)
        self.results.append(model)


    def fitEnsemble(self, normMean, samples, labels, factor):
        minWindowLength = 5
        maxWindowLength = min(self.MAX_WINDOW_LENGTH, samples.shape[1])
        windows = [i for i in range(minWindowLength, maxWindowLength+1)]

        correctTraining = 0
        self.results = []

        print(self.NAME+"  Fitting for a norm of "+str(normMean))
        with progressbar.ProgressBar(max_value=len(windows)) as bar:
            Parallel(n_jobs=3, backend="threading")(delayed(self.fitIndividual, check_pickle=False)(normMean, samples, labels, windows, i, bar) for i in range(len(windows)))
        print()

        # Find best correctTraining
        for i in range(len(self.results)):
            if self.results[i].correct > correctTraining:
                correctTraining = self.results[i].correct

        # Remove Results that are no longer satisfactory
        new_results = []
        for i in range(len(self.results)):
            if self.results[i].correct >= (correctTraining * factor):
                new_results.append(self.results[i])

        return new_results, correctTraining


    def predict(self, model, test_samples, test_labels):
        p = [None for _ in range(len(test_labels))]
        means = [None for _ in range(len(model.labels))]
        stds = [None for _ in range(len(model.labels))]
        means, stds = self.calcMeansStds(model.window, model.samples, means, stds, model.norm)

        for i in range(test_samples.shape[0]):
            query = test_samples.iloc[i,:].tolist()
            distanceTo1NN = math.inf;

            wQueryLen = min(len(query), model.window)
            disjointWindows = getDisjointSequences(query, wQueryLen, model.norm)

            for j in range(len(model.labels)):
                ts = model.samples.iloc[j,:].tolist()
                if ts != query:
                    totalDistance = 0.

                    for q in disjointWindows:
                        resultDistance = distanceTo1NN
                        for w in range(len(ts) - model.window):
                            distance = self.getEuclideanDistance(ts, q, means[j][w], stds[j][w], resultDistance, w)
                            resultDistance = min(distance, resultDistance)
                        totalDistance += resultDistance
                        if totalDistance > distanceTo1NN:
                            break

                    if totalDistance < distanceTo1NN:
                        p[i] = model.labels[j]
                        distanceTo1NN = totalDistance

        correct = sum([p[i] == test_labels[i] for i in range(len(test_labels))])
        return correct, p


    def getEuclideanDistance(self, ts, q, meanTs, stdTs, minValue, w):
        distance = 0.0
        for ww in range(len(q)-1):
            value1 = (ts[w + ww] - meanTs) * stdTs
            value = q[ww] - value1
            distance += value * value

            if distance >= minValue:
                return math.inf
        return distance


    def calcMeansStds(self, windowLength, trainSamples, means, stds, normMean):
        for i in range(trainSamples.shape[0]):
            w = min(windowLength, trainSamples.shape[1])
            means[i] = [None for _ in range(trainSamples.shape[1] - w + 1)]
            stds[i] = [None for _ in range(trainSamples.shape[1] - w + 1)]
            means[i], stds[i] = self.calcIncreamentalMeanStddev(w, trainSamples.iloc[i,:].tolist(), means[i], stds[i])
            for j in range(len(stds[i])):
                stds[i][j] = 1.0 / stds[i][j] if stds[i][j] > 0 else 1.0
                means[i][j] = means[i][j] if normMean else 0
        return means, stds


    def calcIncreamentalMeanStddev(self, windowLength, series, MEANS, STDS):
        SUM = 0.
        squareSum = 0.

        rWindowLength = 1.0 / windowLength
        for ww in range(windowLength):
            SUM += series[ww]
            squareSum += series[ww] * series[ww]
        MEANS[0] = SUM * rWindowLength
        buf = squareSum * rWindowLength - MEANS[0] * MEANS[0]

        STDS[0] = np.sqrt(buf) if buf > 0 else 0

        for w in range(1, (len(series) - windowLength + 1)):
            SUM += series[w + windowLength - 1] - series[w - 1]
            MEANS[w] = SUM * rWindowLength

            squareSum += series[w + windowLength - 1] * series[w + windowLength - 1] - series[w - 1] * series[w - 1]
            buf = squareSum * rWindowLength - MEANS[w] * MEANS[w]
            STDS[w] = np.sqrt(buf) if buf > 0 else 0

        return MEANS, STDS



class ShotgunModel():
    def __init__(self, norm, w, samples, labels):
        self.norm = norm
        self.window = w
        self.samples = samples
        self.labels = labels
        self.correct = None