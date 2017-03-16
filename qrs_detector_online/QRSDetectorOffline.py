import numpy as np
from scipy.signal import butter, lfilter

class QRSDetectorOffline(object):
    """
    Offline QRS complex detector.

    MIT License

    Copyright (c) 2017 Marta Łukowska, Michał Sznajder

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
    """

    def __init__(self, ecg_data_path, verbose=False):
        """
        QRSDetector class initialisation method.
        """
        # Configuration parameters.
        self.signal_frequency = 250  # Set ECG device frequency in samples per second here.

        self.filter_lowcut = 0.0
        self.filter_highcut = 15.0
        self.filter_order = 1

        self.integration_window = 15  # Change proportionally when adjusting frequency (in samples).

        self.findpeaks_limit = 0.35
        self.findpeaks_spacing = 50  # Change proportionally when adjusting frequency (in samples).
        self.detection_window = 40  # Change proportionally when adjusting frequency (in samples).

        self.refractory_period = 120  # Change proportionally when adjusting frequency (in samples).
        self.signal_peak_filtering_factor = 0.125
        self.noise_peak_filtering_factor = 0.125
        self.signal_noise_diff_weight = 0.25

        # Loaded ECG data.
        self.ecg_data = None

        # Measured and calculated values.
        self.filtered_signal = None
        self.differentiated_signal = None
        self.squared_signal = None
        self.integrated_signal = None
        self.detected_peaks_indices = None
        self.detected_peaks_values = None

        self.qrs_peaks_indices = np.array([])
        self.noise_peaks_indices = np.array([])

        self.signal_peak_value = 0.0
        self.noise_peak_value = 0.0
        self.threshold_value = 0.0

        # Load data and run the detection flow.
        self.load_ecg_data(ecg_data_path)
        self.detect_peaks(self.ecg_data)
        self.detect_qrs(detected_peaks_indices=self.detected_peaks_indices,
                        detected_peaks_values=self.detected_peaks_values)

        if verbose:
            print("qrs peaks indices")
            print(self.qrs_peaks_indices)
            print("noise peaks indices")
            print(self.noise_peaks_indices)

        # TODO: Create as a result field where user can read the detected data array as in logged format - after detection.

    """Loading ECG measurements data methods."""

    def load_ecg_data(self, ecg_data_path):
        self.ecg_data = np.loadtxt(ecg_data_path, skiprows=1, delimiter=',')

    """ECG measurements data processing methods."""

    def detect_peaks(self, ecg_data):
        """
        Method responsible for extracting peaks from loaded ECG measurements data through signal processing.
        :param array ecg_data: most recent ECG measurements array
        """

        # Extract measurements from loaded ECG data.
        ecg_measurements = ecg_data[:, 1]

        # Signal filtering - 0-15 Hz band pass filter.
        self.filtered_signal = self.bandpass_filter(ecg_measurements, lowcut=self.filter_lowcut,
                                               highcut=self.filter_highcut, signal_freq=self.signal_frequency,
                                               filter_order=self.filter_order)

        # Derivative - provides QRS slope information.
        self.differentiated_signal = np.ediff1d(self.filtered_signal)

        # Squaring - intensifies values received in derivative.
        self.squared_signal = self.differentiated_signal ** 2

        # Moving-window integration.
        self.integrated_signal = np.convolve(self.squared_signal, np.ones(self.integration_window))

        # Fiducial mark - peak detection on integrated signal.
        self.detected_peaks_indices = self.findpeaks(data=self.integrated_signal,
                                                limit=self.findpeaks_limit,
                                                spacing=self.findpeaks_spacing)

        self.detected_peaks_values = self.integrated_signal[self.detected_peaks_indices]

    """QRS detection methods."""

    def detect_qrs(self, detected_peaks_indices, detected_peaks_values):
        """
        Method responsible for classifying detected ECG signal peaks either as noise or as QRS complex (heart beat).
        :param array detected_peaks_values: detected peaks values array
        """
        for detected_peak_index, detected_peaks_value in zip(detected_peaks_indices, detected_peaks_values):

            try:
                last_qrs_index = self.qrs_peaks_indices[-1]
            except IndexError:
                last_qrs_index = 0

            # After a valid QRS complex detection, there is a 200 ms refractory period before next one can be detected.
            if detected_peak_index - last_qrs_index > self.refractory_period or not self.qrs_peaks_indices.size:
                # Peak must be classified either as a noise peak or a signal peak.
                # To be classified as a signal peak (QRS peak) it must exceed dynamically set threshold value.
                if detected_peaks_value > self.threshold_value:
                    self.qrs_peaks_indices = np.append(self.qrs_peaks_indices, detected_peak_index)

                    # Adjust signal peak value used later for setting QRS-noise threshold.
                    self.signal_peak_value = self.signal_peak_filtering_factor * detected_peaks_value + \
                                             (1 - self.signal_peak_filtering_factor) * self.signal_peak_value
                else:
                    self.noise_peaks_indices = np.append(self.noise_peaks_indices, detected_peak_index)

                    # Adjust noise peak value used later for setting QRS-noise threshold.
                    self.noise_peak_value = self.noise_peak_filtering_factor * detected_peaks_value + \
                                            (1 - self.noise_peak_filtering_factor) * self.noise_peak_value

                # Adjust QRS-noise threshold value based on previously detected QRS or noise peaks value.
                self.threshold_value = self.noise_peak_value + \
                                       self.signal_noise_diff_weight * (self.signal_peak_value - self.noise_peak_value)

    """Tools methods."""

    def bandpass_filter(self, data, lowcut, highcut, signal_freq, filter_order):
        """
        Method responsible for creating and applying Butterworth digital filter for received ECG signal.
        :param deque data: raw data
        :param float lowcut: filter lowcut frequency value
        :param float highcut: filter highcut frequency value
        :param int signal_freq: signal frequency in samples per second (Hz)
        :param int filter_order: filter order
        :return array: filtered data
        """
        """Constructs signal filter and uses it to given data set."""
        nyquist_freq = 0.5 * signal_freq
        low = lowcut / nyquist_freq
        high = highcut / nyquist_freq
        b, a = butter(filter_order, [low, high], btype="band")
        y = lfilter(b, a, data)
        return y

    def findpeaks(self, data, spacing=1, limit=None):
        """
        Janko Slavic peak detection algorithm and implementation.
        https://github.com/jankoslavic/py-tools/tree/master/findpeaks
        Finds peaks in `data` which are of `spacing` width and >=`limit`.
        :param ndarray data: data
        :param float spacing: minimum spacing to the next peak (should be 1 or more)
        :param float limit: peaks should have value greater or equal
        :return array: detected peaks indexes array
        """
        len = data.size
        x = np.zeros(len + 2 * spacing)
        x[:spacing] = data[0] - 1.e-6
        x[-spacing:] = data[-1] - 1.e-6
        x[spacing:spacing + len] = data
        peak_candidate = np.zeros(len)
        peak_candidate[:] = True
        for s in range(spacing):
            start = spacing - s - 1
            h_b = x[start: start + len]  # before
            start = spacing
            h_c = x[start: start + len]  # central
            start = spacing + s + 1
            h_a = x[start: start + len]  # after
            peak_candidate = np.logical_and(peak_candidate, np.logical_and(h_c > h_b, h_c > h_a))

        ind = np.argwhere(peak_candidate)
        ind = ind.reshape(ind.size)
        if limit is not None:
            ind = ind[data[ind] > limit]
        return ind


if __name__ == "__main__":
    qrs_detector = QRSDetectorOffline(ecg_data_path="ecg_data/QRS_detector_log_2017_03_06_11_54_02.csv",
                                      verbose=True)
