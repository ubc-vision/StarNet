from starnet.utils.data_utils.restructure_spectrum import continuum_normalize_parallel
from starnet.utils.data_utils.augment import augment_spectra_parallel
from starnet.utils.data_utils.loading import get_synth_wavegrid, get_synth_spec_data, collect_file_list
import numpy as np
import time
import random
import glob
import h5py
import argparse
import uuid
import os
import sys
sys.path.insert(0, os.path.join(os.getenv('HOME'), 'StarNet'))

# Define parameters needed for continuum fitting
LINE_REGIONS = [[4210, 4240], [4250, 4410], [4333, 4388], [4845, 4886], [5160, 5200], [5874, 5916], [6530, 6590]]
SEGMENTS_STEP = 10.  # divide the spectrum into segments of 10 Angstroms


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec_dir', type=str, required=True,
                        help='location where raw spectra are stored')
    parser.add_argument('--save_dir', type=str, required=True,
                        help='temporary location where processed spectra will be saved')
    parser.add_argument('--obs_wave_file', type=str, required=True,
                        help='path of observational wavelength grid')
    parser.add_argument('--max_num_spec', type=int, required=True,
                        help='max number of spectra to store in save_dir')
    parser.add_argument('--synth_wave_file', type=str, default=None,
                        help='path of synthetic wavelength grid (only needed if in separate file)')
    parser.add_argument('-g', '--grid', type=str, default='phoenix',
                        help='name of spectral grid to be used')
    parser.add_argument('-b', '--batch_size', type=int, default=32,
                        help='number of spectra per batch')
    parser.add_argument('-n', '--noise', type=float, default=0.07,
                        help='maximum fractional noise')
    parser.add_argument('-r', '--resolution', type=int, default=47000,
                        help='instrumental resolution to convolve to')
    parser.add_argument('-vrad', '--radial_vel', type=float, default=200.,
                        help='maximum radial velocity (km/s) to modify the spectra with')
    parser.add_argument('-vrot', '--rotational_vel', type=float, default=70.,
                        help='maximum rotational velocity (km/s) to modify the spectra with')
    parser.add_argument('--max_teff', type=float, default=np.Inf,
                        help='maximum temperature (K)')
    parser.add_argument('--min_teff', type=float, default=-np.Inf,
                        help='minimum temperature (K)')
    parser.add_argument('--max_logg', type=float, default=np.Inf,
                        help='maximum logg')
    parser.add_argument('--min_logg', type=float, default=-np.Inf,
                        help='minimum logg')
    parser.add_argument('--max_feh', type=float, default=np.Inf,
                        help='maximum [Fe/H]')
    parser.add_argument('--min_feh', type=float, default=-np.Inf,
                        help='minimum [Fe/H]')
    parser.add_argument('--max_afe', type=float, default=np.Inf,
                        help='maximum [alpha/Fe]')
    parser.add_argument('--min_afe', type=float, default=-np.Inf,
                        help='minimum [alpha/Fe]')
    parser.add_argument('--sigma_gaussian', type=float, default=50.,
                        help='sigma of Gaussian kernel if using Gaussian smoothing'
                             'continuum normalization')

    # Collect arguments
    return parser.parse_args()


def generate_batch(file_list, wave_grid_obs, instrument_res, batch_size=32, max_vrot_to_apply=70,
                   max_vrad_to_apply=200, max_noise=0.07, spectral_grid_name='phoenix', synth_wave_filename=None,
                   max_teff=np.Inf,  min_teff=-np.Inf, max_logg=np.Inf, min_logg=-np.Inf, max_feh=np.Inf,
                   min_feh=-np.Inf, max_afe=np.Inf, min_afe=-np.Inf):

    # Based on the observed wavelength grid, define a wavelength range to slice the synthetic wavelength grid and spectrum
    # (for quicker processing times). Extend on both sides to accommodate radial velocity shifts on synthetic spectra,
    # and also to eliminate edge effects from rotational broadening
    extension = 5  # Angstroms
    wave_min_request = wave_grid_obs[0] - extension
    wave_max_request = wave_grid_obs[-1] + extension

    # This next block of code will iteratively select a random file from the supplied list of synthetic spectra files,
    # extract the flux and stellar parameters from it, and if it falls within the requested parameter space, will
    # append the data to the list of spectra to be modified. It will repeat until the requested batch size has been met.
    t1 = time.time()
    completed = False
    while not completed:
        # Initialize lists
        spectra = []
        wavegrid_synth_list = []
        teff_list = []
        logg_list = []
        vt_list = []
        m_h_list = []
        a_m_list = []
        vrot_list = []
        vrad_list = []
        noise_list = []
        batch_file_list = []

        while np.shape(spectra)[0] < batch_size:
            # Randomly collect a file from the whole list of synthetic spectra files
            batch_index = random.choice(range(0, len(file_list)))
            batch_file = file_list[batch_index]

            # Collect flux and stellar parameters from file
            flux, params = get_synth_spec_data(batch_file, spectral_grid_name)
            teff = params['teff']
            logg = params['logg']
            m_h = params['m_h']
            a_m = params['a_m']
            vt = params['vt']
            vrot = params['vrot']

            # Skip if flux is mostly NaNs
            if sum(np.isnan(flux)) > 0.5*len(flux):
                print('Spectrum has too many NaNs! Skipping...')
                print('>>> Spectrum length: {}'.format(len(flux)))
                print('>>> Number of NaNs:  {}'.format(sum(np.isnan(flux))))
                print('>>> Parameters: {} {} {} {}'.format(teff, logg, m_h, a_m, vrot))
                continue

            # Skip this spectrum if beyond requested temperature, logg, or metallicity limits
            if (teff > max_teff) or (teff < min_teff) or (logg > max_logg) or (logg < min_logg) or \
                    (m_h > max_feh) or (m_h < min_feh) or (a_m > max_afe) or (a_m < min_afe):
                continue
            else:
                vrad = random.uniform(-max_vrad_to_apply, max_vrad_to_apply)  # km/s
                noise = np.random.rand() * max_noise

                # Only choose a vrot value if the spectrum wasn't already modified with vrot
                if vrot is np.nan or vrot == 0:
                    vrot = random.uniform(0, max_vrot_to_apply)  # km/s

                # Get synthetic wavelength grid
                # TODO: have these stored in data directory
                if spectral_grid_name == 'intrigoss' or spectral_grid_name == 'ambre' or spectral_grid_name == 'ferre'\
                        or spectral_grid_name == 'nlte':
                    synth_wave_filename = batch_file
                elif spectral_grid_name == 'phoenix':
                    if synth_wave_filename is None or synth_wave_filename.lower() == 'none':
                        raise ValueError('for Phoenix grid, need to supply separate file containing wavelength grid')
                else:
                    synth_wave_filename = None
                wave_grid_synth = get_synth_wavegrid(synth_wave_filename, spectral_grid_name)

                # Trim wave grid and flux array
                wave_indices = (wave_grid_synth > wave_min_request) & (wave_grid_synth < wave_max_request)
                wave_grid_synth = wave_grid_synth[wave_indices]
                flux = flux[wave_indices]

                # Check for repeating wavelengths and remove them
                dw = wave_grid_synth[1:] - wave_grid_synth[:-1]
                idx = np.where(dw == 0)[0]
                if len(idx) > 0:
                    wave_grid_synth = np.delete(wave_grid_synth, idx[0])
                    flux = np.delete(flux, idx[0])

                # Fill up lists
                spectra.append(flux)
                wavegrid_synth_list.append(wave_grid_synth)
                teff_list.append(teff)
                logg_list.append(logg)
                m_h_list.append(m_h)
                a_m_list.append(a_m)
                vt_list.append(vt)
                vrot_list.append(vrot)
                vrad_list.append(vrad)
                noise_list.append(noise)
                batch_file_list.append(batch_file)
        t2 = time.time()
        print('Time taken to collect spectra: %.1f s' % (t2 - t1))
        print('File paths for collected spectra: {}'.format(batch_file_list))

        # Modify the rotational velocity only if the spectra aren't already modified
        if max_vrot_to_apply > 0:
            modify_vrot_list = vrot_list
        else:
            modify_vrot_list = np.zeros(len(vrot_list))

        t1 = time.time()
        # Modify spectra in parallel (degrade resolution, apply rotational broadening, etc.)
        spectra = augment_spectra_parallel(spectra, wavegrid_synth_list, wave_grid_obs, modify_vrot_list, noise_list,
                                           vrad_list, instrument_res)
        print('Total modify time: %.1f s' % (time.time() - t1))

        # Continuum normalize spectra with asymmetric sigma clipping continuum fitting method
        t1 = time.time()
        spectra_asym_sigma = continuum_normalize_parallel(spectra, wave_grid_obs,
                                                          line_regions=LINE_REGIONS,
                                                          segments_step=SEGMENTS_STEP,
                                                          fit='asym_sigmaclip',
                                                          sigma_upper=2.0, sigma_lower=0.5)

        print('Total continuum time: %.2f s' % (time.time() - t1))

        # Check again for nans
        nan_problem = False
        for f in spectra:
            if sum(np.isnan(f)) > 0.5 * len(f):
                print('Spectrum has too many NaNs! Collecting another batch...')
                nan_problem = True
            else:
                continue
        if not nan_problem:
            completed = True

        params = teff_list, logg_list, m_h_list, a_m_list, vt_list, vrot_list, vrad_list, noise_list
    return spectra_asym_sigma, params


def main():

    # Collect arguments
    args = parse_args()

    # Check if supplied grid name is valid
    grid_name = args.grid.lower()
    if grid_name not in ['intrigoss', 'phoenix', 'ambre', 'ferre', 'nlte', 'mpia']:
        raise ValueError('{} not a valid grid name. Need to supply an appropriate spectral grid name '
                         '(phoenix, intrigoss, ferre, or ambre)'.format(grid_name))

    # Collect list of files containing the spectra
    file_list = collect_file_list(grid_name, args.spec_dir)

    # Get observational wavelength grid (stored in saved numpy array)
    wave_grid_obs = np.load(args.obs_wave_file)

    # Determine total number of spectra already in chosen directory
    total_num_spec = 0
    existing_files = glob.glob(args.save_dir + '/*')
    if len(existing_files) > 0:
        for f in existing_files:
            f = os.path.basename(f)
            num_spec_in_file = int(f[37:])  # Number of spectra appended on to end of filename
            total_num_spec += num_spec_in_file
    print('Number of spectra already processed: {}/{}'.format(total_num_spec, args.max_num_spec))

    # Generate the batches of spectra
    spectra_created = 0
    while total_num_spec <= args.max_num_spec:

        if total_num_spec >= args.max_num_spec:
            print('Maximum number of spectra reached.')
            break

        # Process a batch of raw synthetic spectra
        t0_batch = time.time()
        print('Creating a batch of spectra...')
        spec_asym, params = generate_batch(file_list, wave_grid_obs, args.resolution,
                                                   batch_size=args.batch_size,
                                                   max_vrot_to_apply=args.rotational_vel,
                                                   max_vrad_to_apply=args.radial_vel,
                                                   max_noise=args.noise,
                                                   spectral_grid_name=grid_name,
                                                   synth_wave_filename=args.synth_wave_file,
                                                   max_teff=args.max_teff,
                                                   min_teff=args.min_teff,
                                                   max_logg=args.max_logg,
                                                   min_logg=args.min_logg,
                                                   max_feh=args.max_feh,
                                                   min_feh=args.min_feh)
        teff, logg, m_h, a_m, vt, vrot, vrad, noise = params

        # Save this batch to an h5 file in chosen save directory
        if not os.path.exists(args.save_dir):
            os.makedirs(args.save_dir)
        unique_filename = str(uuid.uuid4()) + '_{}'.format(args.batch_size)
        save_path = os.path.join(args.save_dir, unique_filename)
        print('Saving {} to {}'.format(unique_filename, args.save_dir))
        with h5py.File(save_path, 'w') as f:
            f.create_dataset('spectra_asymnorm', data=np.asarray(spec_asym))
            #f.create_dataset('spectra_gaussiannorm', data=np.asarray(spec_g))
            f.create_dataset('teff', data=np.asarray(teff))
            f.create_dataset('logg', data=np.asarray(logg))
            f.create_dataset('M_H', data=np.asarray(m_h))
            f.create_dataset('a_M', data=np.asarray(a_m))
            f.create_dataset('VT', data=np.asarray(vt))
            f.create_dataset('v_rot', data=np.asarray(vrot))
            f.create_dataset('v_rad', data=np.asarray(vrad))
            f.create_dataset('noise', data=np.asarray(noise))
            f.create_dataset('wave_grid', data=np.asarray(wave_grid_obs))
        print('Total time to make this batch of {} spectra: {:.1f}'.format(args.batch_size, time.time() - t0_batch))

        spectra_created += args.batch_size
        print('Total # of spectra created so far: {}'.format(spectra_created))

        # Again, check to see how many files are in the chosen save directory (parallel jobs will be filling it up too)
        total_num_spec = 0
        existing_files = glob.glob(args.save_dir + '/*')
        for f in existing_files:
            f = os.path.basename(f)
            num_spec_in_file = int(f[37:])  # Number of spectra appended on to end of filename
            total_num_spec += num_spec_in_file
        print('Total # of spectra in directory: {}/{}'.format(total_num_spec, args.max_num_spec))


if __name__ == '__main__':
    main()
